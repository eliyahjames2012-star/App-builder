# A.E.G.I.S. Control V3
# Run this file in Pydroid 3. Standard-library-only Tkinter interface.
# Pixel fonts deliberately avoid Android/Tk point-font scaling differences.
# Device controls remain placeholders until an Android bridge is connected.

import math
import time
import tkinter as tk
from tkinter import messagebox

BG = "#030b12"
CYAN = "#72f6ff"
WHITE = "#e4f8ff"
MUTED = "#7da5b7"
AMBER = "#ffc766"
GREEN = "#5bffb2"
HOLD_SECONDS = 2.0
SHUTDOWN_SECONDS = 1.8
STARTUP_SECONDS = 4.2


def clamp(value):
    return max(0.0, min(1.0, value))


def smooth(value):
    value = clamp(value)
    return value * value * (3 - 2 * value)


def mix(color, amount):
    """Fade a hex color toward the background."""
    amount = clamp(amount)
    rgb = [round(int(BG[i:i+2], 16) +
                 (int(color[i:i+2], 16)-int(BG[i:i+2], 16))*amount)
           for i in (1, 3, 5)]
    return "#" + "".join(f"{v:02x}" for v in rgb)


class AegisApp:
    def __init__(self, root):
        self.root = root
        root.title("A.E.G.I.S. CONTROL V3")
        root.configure(bg=BG)
        root.geometry("430x850")
        root.minsize(240, 440)
        self.state = "starting"
        self.state_started = time.monotonic()
        self.pressed_target = None
        self.press_started = None
        self.hover_target = None
        self.hold_consumed = False
        self.hit_regions = {}
        self.messages = []
        self.controls = [
            ("flashlight", "FLASHLIGHT", self.flashlight),
            ("sound", "VOLUME", lambda: self.open_setting("sound")),
            ("bluetooth", "BLUETOOTH", lambda: self.open_setting("bluetooth")),
            ("apps", "APPS", self.app_launcher),
            ("wifi", "WI-FI", lambda: self.open_setting("wifi")),
            ("display", "DISPLAY", lambda: self.open_setting("display")),
        ]
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0,
                                takefocus=True, width=240, height=440)
        self.canvas.pack(fill="both", expand=True)
        self.command_row = tk.Frame(self.canvas, bg="#0d1d2a")
        self.command_entry = tk.Entry(
            self.command_row, bg="#102635", fg=WHITE, insertbackground=WHITE,
            relief="flat", bd=0, highlightthickness=0, font=("Arial", -12))
        self.command_entry.pack(side="left", fill="both", expand=True)
        self.command_entry.insert(0, "help")
        self.command_entry.bind("<Return>", lambda _e: self.run_command())
        self.run_button = tk.Button(
            self.command_row, text="RUN", command=self.run_command,
            bg="#14506a", fg=WHITE, activebackground="#237a96",
            activeforeground=WHITE, relief="flat", bd=0,
            font=("Arial", -11, "bold"))
        self.run_button.pack(side="right", fill="y", padx=(5, 0))
        # Keep the native entry window alive between frames. Recreating it
        # every animation tick can cause blank controls and lost keyboard focus.
        self.command_window = self.canvas.create_window(
            0, 0, window=self.command_row, state="hidden")
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", self._leave)
        self.canvas.bind("<FocusOut>", lambda _e: self._cancel_press())
        self.canvas.bind("<Escape>", lambda _e: self._cancel_press())
        self.canvas.bind("<Return>", lambda _e: self._core_tap())
        self.canvas.bind("<space>", lambda _e: self._core_tap())
        self.canvas.bind("<Configure>", lambda _e: self._draw(time.monotonic()))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.running = True
        self.log("Orbital interface initialized.")
        self.log("Android bridge offline. Hardware controls not connected.")
        self._animate()

    def log(self, message):
        self.messages.append(f"[{time.strftime('%H:%M:%S')}] {message}")
        self.messages = self.messages[-60:]

    def _transition(self, state, now=None):
        self.state = state
        self.state_started = time.monotonic() if now is None else now
        self._cancel_press()
        self.hover_target = None
        self.canvas.configure(cursor="")
        self.command_entry.configure(state="normal" if state == "online" else "disabled")
        if state != "online":
            self.canvas.itemconfigure(self.command_window, state="hidden")
        if state == "collapsing":
            self.log("Interface powering down. Model and files unaffected.")
        elif state == "starting":
            self.log("Core ignition. Rebuilding orbital interface.")
        elif state == "online":
            self.log("Interface online. Hold core for 2 seconds to power down.")

    def _advance(self, now):
        if (self.state == "online" and self.pressed_target == "core"
                and self.press_started is not None
                and now-self.press_started >= HOLD_SECONDS):
            self.hold_consumed = True
            self._transition("collapsing", now)
        elapsed = now-self.state_started
        if self.state == "collapsing" and elapsed >= SHUTDOWN_SECONDS:
            self._transition("off", now)
        elif self.state == "starting" and elapsed >= STARTUP_SECONDS:
            self._transition("online", now)

    def _animate(self):
        if not self.running:
            return
        now = time.monotonic()
        self._advance(now)
        self._draw(now)
        self.animation_job = self.root.after(33, self._animate)

    def _draw(self, now):
        c = self.canvas
        c.delete("scene")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 20 or h < 20:
            return
        # A single virtual coordinate system keeps every platform proportional.
        base = min(w/420, h/820)
        cx, cy = w/2, (h-820*base)/2+390*base
        elapsed = max(0, now-self.state_started)
        p = 1.0
        alpha = 1.0
        if self.state == "collapsing":
            t = clamp(elapsed/SHUTDOWN_SECONDS)
            p = max(0.001, 1-smooth(t))
            alpha = 1-smooth((t-0.45)/0.55)
        elif self.state == "starting":
            t = clamp(elapsed/STARTUP_SECONDS)
            p = 0.04+0.96*smooth((t-0.18)/0.70)
            alpha = smooth((t-0.10)/0.65)
        self.scale = base*p
        self.cx, self.cy = cx, cy
        self.alpha = alpha
        self.hit_regions = {}
        if self.state != "off":
            self._scene(now, base)
        if self.state in ("starting", "collapsing"):
            self._effects(now, elapsed, base)
        if self.state == "off":
            self._off_core(now, base)
        if self.state == "online":
            self.command_entry.configure(font=("Arial", -max(8, round(12*base))))
            self.run_button.configure(font=("Arial", -max(8, round(11*base)), "bold"))
            x, y = self._xy(210, 763)
            c.coords(self.command_window, x, y)
            c.itemconfigure(self.command_window, width=round(364*base),
                            height=round(29*base), state="normal")
            c.tag_raise(self.command_window)
        c.addtag_all("scene")
        c.dtag(self.command_window, "scene")

    def _xy(self, x, y):
        return self.cx+(x-210)*self.scale, self.cy+(y-390)*self.scale

    def _coords(self, points):
        result = []
        for x, y in zip(points[::2], points[1::2]):
            result.extend(self._xy(x, y))
        return result

    def _line(self, *points, color=CYAN, width=1):
        return self.canvas.create_line(
            *self._coords(points), fill=mix(color, self.alpha),
            width=max(1, width*self.scale), capstyle="round")

    def _oval(self, x, y, radius, color=CYAN, fill=None, width=1):
        return self.canvas.create_oval(
            *self._coords((x-radius, y-radius, x+radius, y+radius)),
            outline=mix(color, self.alpha) if color else "",
            fill=mix(fill, self.alpha) if fill else "",
            width=max(1, width*self.scale))

    def _rect(self, x1, y1, x2, y2, color=CYAN, fill=None):
        return self.canvas.create_rectangle(
            *self._coords((x1, y1, x2, y2)),
            outline=mix(color, self.alpha) if color else "",
            fill=mix(fill, self.alpha) if fill else "")

    def _arc(self, x, y, r, start, extent, color=CYAN, width=2):
        return self.canvas.create_arc(
            *self._coords((x-r, y-r, x+r, y+r)), start=start,
            extent=extent, style="arc", outline=mix(color, self.alpha),
            width=max(1, width*self.scale))

    def _text(self, x, y, text, size=10, color=MUTED, anchor="center",
              max_width=None, bold=False):
        # NEGATIVE font sizes are pixels, not DPI-scaled Tk points.
        px = max(1, round(size*self.scale))
        item = self.canvas.create_text(
            *self._xy(x, y), text=text, fill=mix(color, self.alpha),
            font=("Arial", -px, "bold" if bold else "normal"), anchor=anchor)
        if max_width:
            limit = max_width*self.scale
            bounds = self.canvas.bbox(item)
            while px > 1 and bounds and bounds[2]-bounds[0] > limit:
                px -= 1
                self.canvas.itemconfigure(
                    item, font=("Arial", -px, "bold" if bold else "normal"))
                bounds = self.canvas.bbox(item)
        return item

    def _scene(self, now, base):
        self._text(18, 31, "A.E.G.I.S.", 29, CYAN, "w", bold=True)
        self._text(18, 56, "PERSONAL DEVICE CONTROL / ORBITAL INTERFACE",
                   10, anchor="w", max_width=384)
        self._text(210, 83, "LOCAL UI ONLINE  |  ANDROID BRIDGE OFFLINE",
                   11, AMBER, max_width=380)
        for x in range(12, 409, 28):
            self._line(x, 105, x, 652, color="#071720")
        for y in range(105, 653, 28):
            self._line(12, y, 408, y, color="#071720")
        for x, dx in ((12, 1), (408, -1)):
            for y, dy in ((105, 1), (652, -1)):
                self._line(x, y+18*dy, x, y, x+18*dx, y, color="#20556b")
        self._text(210, 124, "N E U R A L   I N T E R F A C E",
                   11, max_width=330)
        self._oval(210, 390, 150, "#123442")
        self._oval(210, 390, 113, "#0d2d3b")
        for i in range(72):
            a = math.radians(i*5)
            r = 99 if i % 3 == 0 else 103
            self._line(210+math.cos(a)*r, 390+math.sin(a)*r,
                       210+math.cos(a)*107, 390+math.sin(a)*107,
                       color="#28657b" if i % 3 == 0 else "#123a4a")
        phase = (now*38) % 360
        if self.state == "starting":
            phase += 400*(1-clamp((now-self.state_started)/STARTUP_SECONDS))
        elif self.state == "collapsing":
            phase += 300*(now-self.state_started)
        for radius, width, step, extent, speed in (
                (93, 3, 120, 83, 1), (82, 2, 90, 59, -0.7),
                (63, 4, 120, 100, 0.45)):
            for start in range(0, 360, step):
                self._arc(210, 390, radius, start+phase*speed, extent, width=width)
        self._oval(210, 390, 73, "#1b5267")
        breath = math.sin(now*2.3)
        for r, color in ((54, "#082533"), (47, "#0a3748"),
                         (39+breath*2, "#10566b"), (30+breath, "#20899b"),
                         (22, "#62dce7"), (13, "#c4fbff")):
            self._oval(210, 390, r, None, color)
        self._oval(210, 390, 47)
        self._oval(210, 390, 22, "#b7faff")
        if self.state == "online":
            self.hit_regions["core"] = (self.cx, self.cy, 108*self.scale)
        for i, (key, label, _command) in enumerate(self.controls):
            a = math.radians(-90+i*60)
            x, y = 210+math.cos(a)*150, 390+math.sin(a)*150
            self._line(210+math.cos(a)*114, 390+math.sin(a)*114,
                       x, y, color="#20586a")
            active = key in (self.hover_target, self.pressed_target)
            self._oval(x, y, 33, "#24586a")
            self._oval(x, y, 29, WHITE if active else "#46b7ce",
                       "#123b4c" if active else "#081d29", 1.5)
            self._icon(key, x, y, WHITE if active else CYAN)
            self._text(x, y+43, label, 11, WHITE if active else MUTED,
                       max_width=100, bold=True)
            if self.state == "online":
                px, py = self._xy(x, y)
                self.hit_regions[key] = (px, py, 33*self.scale)
        hold = (clamp((now-self.press_started)/HOLD_SECONDS)
                if self.press_started is not None and self.pressed_target == "core"
                else 0)
        if hold:
            self._arc(210, 390, 117, 90, -359.9*hold, AMBER, 4)
        self._text(210, 615, "HOLD TO POWER DOWN" if hold else "CORE ONLINE",
                   11, AMBER if hold else CYAN, bold=True, max_width=330)
        self._text(210, 636, "HOLD CORE 2s TO SHUT DOWN / TAP TO RESTART",
                   10, max_width=365)
        self._rect(14, 671, 406, 789, "#1c5268", "#0d1d2a")
        self._text(26, 688, "COMMAND CONSOLE", 10, CYAN, "w", bold=True)
        self._rect(24, 701, 396, 741, "#164052", "#061018")
        for index, message in enumerate(self.messages[-3:]):
            self._text(30, 709+12*index, message, 10, GREEN, "w", max_width=360)
        if self.state != "online":
            self._rect(28, 749, 392, 778, "#164052", "#102635")
            self._text(38, 763, "COMMAND CHANNEL", 9, MUTED, "w")
        self._text(210, 806, "LOCAL ONLY / MODEL AND FILES UNCHANGED",
                   10, max_width=380)

    def _icon(self, key, x, y, color):
        def line(*pts):
            coords = []
            for xx, yy in zip(pts[::2], pts[1::2]):
                coords.extend((x+xx, y+yy))
            self._line(*coords, color=color, width=1.7)

        if key == "flashlight":
            line(-9, -9, 9, -9, 5, -2, 5, 13, -5, 13, -5, -2, -9, -9)
            line(-9, -12, 9, -12)
            line(-3, -17, -5, -21)
            line(3, -17, 5, -21)
            line(-2, 2, 2, 2)
        elif key == "sound":
            line(-13, -5, -7, -5, 0, -12, 0, 12, -7, 5, -13, 5, -13, -5)
            self._arc(x+4, y, 8, -65, 130, color)
            self._arc(x+7, y, 14, -60, 120, color)
        elif key == "bluetooth":
            line(-8, -9, 8, 7, 0, 15, 0, -15, 8, -7, -8, 9)
        elif key == "apps":
            for xx in (-12, 3):
                for yy in (-12, 3):
                    self._rect(x+xx, y+yy, x+xx+9, y+yy+9, color)
        elif key == "wifi":
            for r in (7, 13, 19):
                self._arc(x, y+5, r, 40, 100, color)
            self._oval(x, y+9, 2, None, color)
        elif key == "display":
            self._oval(x, y, 7, color)
            for a in range(0, 360, 45):
                a = math.radians(a)
                line(math.cos(a)*11, math.sin(a)*11,
                     math.cos(a)*16, math.sin(a)*16)

    def _effects(self, now, elapsed, base):
        """Deterministic spiraling particles and outward ignition shockwave."""
        c = self.canvas
        starting = self.state == "starting"
        t = clamp(elapsed/(STARTUP_SECONDS if starting else SHUTDOWN_SECONDS))
        for i in range(60):
            offset = ((i*0.61803398875) % 1)
            travel = clamp((t-offset*0.28)/0.72)
            radius = (12+travel*290 if starting else 290*(1-travel))*base
            angle = i*2.39996 + (travel*3 if starting else travel*5)
            x, y = self.cx+math.cos(angle)*radius, self.cy+math.sin(angle)*radius
            tail = radius+(9*base if not starting else -9*base)
            opacity = math.sin(math.pi*travel)
            c.create_line(x, y, self.cx+math.cos(angle-0.025)*tail,
                          self.cy+math.sin(angle-0.025)*tail,
                          fill=mix(CYAN, opacity), width=max(1, base))
        if starting:
            wave = clamp((t-0.10)/0.45)
            r = (15+wave*360)*base
            c.create_oval(self.cx-r, self.cy-r, self.cx+r, self.cy+r,
                          outline=mix(WHITE, (1-wave)*0.8), width=max(1, 2*base))
            glow = (17+20*math.sin(math.pi*clamp(t/0.4)))*base
        else:
            glow = (10+30*math.sin(math.pi*t))*base
        if t < 0.88 or not starting:
            c.create_oval(self.cx-glow, self.cy-glow, self.cx+glow, self.cy+glow,
                          outline=mix(CYAN, 0.7), fill="#103344", width=2)
            r = glow*0.42
            c.create_oval(self.cx-r, self.cy-r, self.cx+r, self.cy+r,
                          fill=WHITE, outline="")
        if starting:
            steps = ("CORE IGNITION", "ENERGY FIELD STABILIZING",
                     "REBUILDING INTERFACE", "SYNCHRONIZING CONTROLS",
                     "SYSTEM READY")
            caption = steps[min(4, int(t*5))]
        else:
            caption = "COLLAPSING INTERFACE" if t < 0.75 else "CORE SEALED"
        c.create_text(self.cx, self.cy+206*base, text=caption,
                      fill=CYAN, font=("Arial", -max(7, round(10*base)), "bold"))

    def _off_core(self, now, base):
        c = self.canvas
        r = (19+math.sin(now*1.7))*base
        c.create_oval(self.cx-r-5*base, self.cy-r-5*base,
                      self.cx+r+5*base, self.cy+r+5*base, outline="#173948")
        c.create_oval(self.cx-r, self.cy-r, self.cx+r, self.cy+r,
                      fill="#081d29", outline="#3f8497", width=max(1, base))
        c.create_oval(self.cx-5*base, self.cy-5*base,
                      self.cx+5*base, self.cy+5*base, fill="#72bdcc", outline="")
        c.create_text(self.cx, self.cy+58*base, text="PRESS CORE TO START",
                      fill=MUTED, font=("Arial", -max(7, round(10*base))))
        self.hit_regions = {"core": (self.cx, self.cy, max(24, 36*base))}

    def _target_at(self, event):
        for key, (x, y, r) in self.hit_regions.items():
            if (event.x-x)**2+(event.y-y)**2 <= r*r:
                return key
        return None

    def _press(self, event):
        self.canvas.focus_set()
        self.pressed_target = self._target_at(event)
        self.hold_consumed = False
        self.press_started = time.monotonic() if self.pressed_target == "core" else None

    def _release(self, event):
        target = self._target_at(event)
        pressed = self.pressed_target
        consumed = self.hold_consumed
        self._cancel_press()
        if consumed or target is None or target != pressed:
            return
        if target == "core":
            self._core_tap()
        elif self.state == "online":
            for key, _label, callback in self.controls:
                if key == target:
                    callback()
                    break

    def _core_tap(self):
        if self.state == "off":
            self._transition("starting")
        elif self.state == "online":
            self.log("Core online. Hold for 2 seconds to power down.")

    def _cancel_press(self):
        self.pressed_target = None
        self.press_started = None

    def _motion(self, event):
        target = self._target_at(event)
        self.hover_target = target
        self.canvas.configure(cursor="hand2" if target else "")
        if self.pressed_target and target != self.pressed_target:
            self._cancel_press()

    def _leave(self, _event):
        self.hover_target = None
        self._cancel_press()
        self.canvas.configure(cursor="")

    def flashlight(self):
        self.log("Flashlight requested. Android bridge required.")
        messagebox.showinfo("Flashlight",
                            "The flashlight icon is ready. Turning on the phone's "
                            "torch still requires an Android companion bridge.")

    def open_setting(self, kind):
        label = {"sound": "Volume", "display": "Display",
                 "wifi": "Wi-Fi", "bluetooth": "Bluetooth"}.get(kind, kind)
        self.log(f"{label} requested. Android bridge required.")messagebox.showinfo(label, "Opening Android settings requires the "
                            "native companion bridge. No device setting changed.")

    def app_launcher(self):
        self.log("App launcher requested. Android bridge required.")
        messagebox.showinfo("App Launcher",
                            "Launching Android apps requires the companion bridge.")

    def run_command(self):
        if self.state != "online":
            return
        command = self.command_entry.get().strip().lower()
        self.command_entry.delete(0, "end")
        self.log("> "+command)
        if command in ("help", "?"):
            self.log("help, status, flashlight, volume, apps, settings, off")
        elif command == "status":
            self.log("UI online. Android / AI bridges not connected.")
        elif command in ("off", "standby", "shutdown"):
            self._transition("collapsing")
        elif command == "flashlight":
            self.flashlight()
        elif command in ("volume", "sound"):
            self.open_setting("sound")
        elif command == "apps":
            self.app_launcher()
        elif command == "settings":
            self.open_setting("display")
        else:
            self.log("Unknown command. Type help.")

    def close(self):
        self.running = False
        if hasattr(self, "animation_job"):
            self.root.after_cancel(self.animation_job)
        self.root.destroy()


def main():
    root = tk.Tk()
    AegisApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
      
       
