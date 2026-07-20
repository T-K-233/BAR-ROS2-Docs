#!/usr/bin/env python3
"""
Hand-laid SVG diagrams for Humanoid-Control-Website.

Each diagram is a small function that returns an SVG string. Run this file
to regenerate every diagram into ../static/img/diagrams/. The output
filenames match what the markdown references.

The primitive helpers (box, arrow, lane, etc.) are intentionally simple —
they give consistent stroke widths, rounded corners, and a Berkeley
palette across every diagram. The point is not to be a graphing library;
it's to keep the diagrams visually a family.

Palette:
    BLUE     "#003262"    Berkeley blue          structural / control
    GOLD     "#FDB515"    Berkeley gold          policy / external input
    GREEN    "#3B7A57"                           hardware / sim
    RED      "#A00000"                           real hardware / fault
    GREY     "#888888"    neutral                static / inert
    BG       "#FAFAFA"    page background
    TEXT     "#111111"
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "img" / "diagrams"
OUT.mkdir(parents=True, exist_ok=True)

# Palette ----------------------------------------------------------------------
BLUE = "#003262"
GOLD = "#FDB515"
GREEN = "#3B7A57"
RED = "#A00000"
GREY = "#888888"
LIGHT = "#EEEEEE"
TEXT = "#111111"

# A subdued fill for each accent (use as box background; stroke = the
# strong color). Eyeballed for legibility on a white page.
BLUE_FILL = "#E7F0FF"
GOLD_FILL = "#FFF6DF"
GREEN_FILL = "#E7FFE7"
RED_FILL = "#FFE7E7"
GREY_FILL = "#F4F4F4"

# Font stack uses only space-free family names so we don't need internal
# quoting inside the SVG `font-family` attribute. Anything that has a
# space (e.g. "JetBrains Mono") would need &apos;/&quot; escaping in XML —
# avoided entirely here by sticking to single-token names + the generic
# monospace fallback.
FONT = "ui-monospace, Menlo, Consolas, Courier, monospace"

# --- Primitives --------------------------------------------------------------

def header(w: int, h: int) -> str:
    """SVG root + defs (one arrow-marker is enough)."""
    return dedent(f"""\
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"
             width="{w}" height="{h}" font-family="{FONT}"
             font-size="13" fill="{TEXT}" text-rendering="geometricPrecision">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5"
                    markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="{TEXT}"/>
            </marker>
            <marker id="arrow-grey" viewBox="0 0 10 10" refX="9" refY="5"
                    markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="{GREY}"/>
            </marker>
          </defs>
          <rect width="100%" height="100%" fill="white"/>
    """)

def footer() -> str:
    return "</svg>\n"


def text(x: int, y: int, s: str, *, size: int = 13, weight: int = 400,
         anchor: str = "start", fill: str = TEXT) -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
        f'text-anchor="{anchor}" fill="{fill}" '
        f'dominant-baseline="middle">{s}</text>'
    )


def multiline_text(x: int, y: int, lines: list[str], *, size: int = 13,
                   weight: int = 400, anchor: str = "middle",
                   fill: str = TEXT, lh: float = 1.25) -> str:
    """Several centered text lines starting at (x, y)."""
    total = len(lines)
    start_y = y - (total - 1) * size * lh / 2
    out = []
    for i, line in enumerate(lines):
        out.append(text(x, int(start_y + i * size * lh), line,
                        size=size, weight=weight, anchor=anchor, fill=fill))
    return "\n".join(out)


@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int
    label: str | list[str]  # multi-line allowed via list
    fill: str = "white"
    stroke: str = BLUE
    text_color: str = TEXT
    radius: int = 6
    sub: str | None = None  # optional subtitle below the main label

    @property
    def cx(self) -> int: return self.x + self.w // 2
    @property
    def cy(self) -> int: return self.y + self.h // 2
    @property
    def right(self) -> int: return self.x + self.w
    @property
    def bottom(self) -> int: return self.y + self.h
    @property
    def left(self) -> int: return self.x
    @property
    def top(self) -> int: return self.y

    def render(self) -> str:
        rect = (
            f'<rect x="{self.x}" y="{self.y}" width="{self.w}" height="{self.h}" '
            f'rx="{self.radius}" ry="{self.radius}" fill="{self.fill}" '
            f'stroke="{self.stroke}" stroke-width="1.5"/>'
        )
        if isinstance(self.label, list):
            lines = self.label
        else:
            lines = [self.label]
        # Place sub line slightly below main lines
        label_lines = list(lines)
        labels = multiline_text(
            self.cx, self.cy if not self.sub else self.cy - 8,
            label_lines, size=13, weight=600, fill=self.text_color
        )
        sub = ""
        if self.sub:
            sub_y = self.cy + 10 + (len(lines) - 1) * 8
            sub = text(self.cx, sub_y, self.sub, size=11, weight=400,
                       anchor="middle", fill=GREY)
        return f"{rect}\n{labels}\n{sub}"


def arrow(x1: int, y1: int, x2: int, y2: int, *, color: str = TEXT,
          dashed: bool = False, width: float = 1.4,
          label: str | None = None, label_pos: float = 0.5,
          label_offset: int = -8) -> str:
    marker = "url(#arrow)" if color == TEXT else "url(#arrow-grey)"
    dash = ' stroke-dasharray="4 3"' if dashed else ""
    line = (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
        f'stroke-width="{width}"{dash} marker-end="{marker}"/>'
    )
    if label is None:
        return line
    mx = int(x1 + (x2 - x1) * label_pos)
    my = int(y1 + (y2 - y1) * label_pos) + label_offset
    label_node = text(
        mx, my, label, size=11, anchor="middle", fill=GREY,
    )
    # tiny rounded background pill so the label reads over arrow line
    pad = 4
    approx_w = max(20, int(len(label) * 6) + pad * 2)
    bg = (
        f'<rect x="{mx - approx_w // 2}" y="{my - 8}" width="{approx_w}" '
        f'height="16" rx="3" ry="3" fill="white" stroke="none"/>'
    )
    return f"{line}\n{bg}\n{label_node}"


def polyline(points: list[tuple[int, int]], *, color: str = TEXT,
             dashed: bool = False, width: float = 1.4,
             arrow_end: bool = True) -> str:
    """Multi-segment line; arrow at the end if requested."""
    if not points or len(points) < 2:
        return ""
    dash = ' stroke-dasharray="4 3"' if dashed else ""
    marker = ' marker-end="url(#arrow)"' if arrow_end else ""
    pts = " ".join(f"{x},{y}" for x, y in points)
    return (
        f'<polyline points="{pts}" fill="none" stroke="{color}" '
        f'stroke-width="{width}"{dash}{marker}/>'
    )


def label_pill(x: int, y: int, s: str, *, fill: str = "white",
               stroke: str = GREY) -> str:
    """Small label with rounded background — for arrow annotations."""
    pad = 6
    w = max(20, len(s) * 6 + pad * 2)
    rect = (
        f'<rect x="{x - w // 2}" y="{y - 9}" width="{w}" height="18" '
        f'rx="4" ry="4" fill="{fill}" stroke="{stroke}" stroke-width="0.8"/>'
    )
    txt = text(x, y, s, size=11, anchor="middle")
    return f"{rect}\n{txt}"


def title(x: int, y: int, s: str, *, sub: str | None = None) -> str:
    """Diagram title (top-left)."""
    out = [text(x, y, s, size=15, weight=700, anchor="start")]
    if sub:
        out.append(text(x, y + 18, sub, size=11, weight=400,
                        anchor="start", fill=GREY))
    return "\n".join(out)


def group_box(x: int, y: int, w: int, h: int, title_: str, *,
              fill: str = LIGHT, stroke: str = GREY) -> str:
    """A grouping box with a small title at top-left."""
    body = (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" ry="8" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1" stroke-dasharray="5 3"/>'
    )
    label = text(x + 12, y + 16, title_, size=11, weight=600,
                 anchor="start", fill=GREY)
    return f"{body}\n{label}"


def _recolor(svg: str) -> str:
    """Map the legacy Berkeley blue/gold palette to the site's orange theme.

    The plain-orange redesign recolored the SVGs by editing them directly and
    never updated this generator, so a naive re-run would revert the theme.
    This bakes the exact same attribute-aware substitution back in (verified to
    reproduce every committed diagram byte-for-byte), so the script self-produces
    the orange theme. To retheme, change only these five rules — the diagram
    functions keep using the semantic BLUE/GOLD/... constants.
    """
    return (svg
            .replace('stroke="#003262"', 'stroke="#ff6633"')   # BLUE stroke -> orange
            .replace('fill="#003262"', 'fill="#cc4a1f"')       # BLUE text  -> dark orange
            .replace('#FDB515', '#5f6671')                     # GOLD -> slate
            .replace('#E7F0FF', '#ffece2')                     # BLUE_FILL -> light orange
            .replace('#FFF6DF', '#eef0f2'))                    # GOLD_FILL -> light slate


def write_svg(name: str, content: str) -> None:
    path = OUT / name
    path.write_text(_recolor(content), encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}")


# --- Diagrams ---------------------------------------------------------------

def d_intro_01_system() -> None:
    """Homepage / intro: 3 vertical lanes (dev / onboard / robot)."""
    W, H = 920, 460
    s = [header(W, H)]
    s.append(title(20, 30, "System at a glance",
                   sub="Developer workstation -> onboard PREEMPT_RT PC -> robot"))

    s.append(group_box(20, 60, 270, 360, "Developer workstation"))
    s.append(group_box(310, 60, 280, 360, "Onboard PC (PREEMPT_RT)"))
    s.append(group_box(610, 60, 290, 360, "Robot (Lite shown)"))

    # Developer
    s.append(Box(50, 100, 210, 50, "IDE / editor",
                 fill=GOLD_FILL, stroke=GOLD).render())
    s.append(Box(50, 170, 210, 70,
                 ["MuJoCo viewer", "(humanoid_bringup_lite/mujoco)"],
                 fill=GOLD_FILL, stroke=GOLD).render())
    s.append(text(155, 300, "Edits, sim runs, debug",
                  size=11, fill=GREY, anchor="middle"))

    # Onboard
    s.append(Box(340, 100, 220, 50, "humanoid_bringup_lite / launch",
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(340, 170, 220, 60, "controller_manager (50 Hz)",
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(340, 250, 100, 50, "joy_teleop",
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(460, 250, 100, 50, "humanoid_control_policy",
                 fill=GOLD_FILL, stroke=GOLD).render())
    s.append(Box(340, 320, 220, 60,
                 ["humanoid_devices_robstride", "(SocketCAN)"],
                 fill=GREEN_FILL, stroke=GREEN).render())

    # Robot
    s.append(Box(635, 100, 240, 50, "IMU (serial / USB)",
                 fill=GREY_FILL, stroke=GREY).render())
    s.append(Box(635, 170, 110, 90, ["can0", "(left arm)"],
                 fill=RED_FILL, stroke=RED).render())
    s.append(Box(765, 170, 110, 90, ["can1", "(right arm)"],
                 fill=RED_FILL, stroke=RED).render())
    s.append(Box(635, 280, 110, 100,
                 ["Robstride x7", "left arm", "+ neck x3"],
                 fill=RED_FILL, stroke=RED).render())
    s.append(Box(765, 280, 110, 100,
                 ["Robstride x7", "right arm"],
                 fill=RED_FILL, stroke=RED).render())

    # Arrows: dev -> onboard
    s.append(arrow(260, 125, 340, 125, label="code", dashed=True,
                   label_offset=-12, color=GREY))
    s.append(arrow(260, 205, 340, 205, label="sim mode", dashed=True,
                   label_offset=-12, color=GREY))
    # Onboard internal
    s.append(arrow(450, 150, 450, 170))  # bringup -> CM
    s.append(arrow(390, 230, 390, 250))  # CM -> joy_teleop
    s.append(arrow(510, 230, 510, 250))  # CM -> policy
    s.append(arrow(510, 300, 510, 320))  # policy -> hw plugin
    # joy_teleop -> CM (switch_controller loop back)
    s.append(polyline([(345, 275), (320, 275), (320, 200), (340, 200)]))
    # Onboard -> robot (CAN)
    s.append(arrow(560, 350, 690, 350, label="MIT-mode CAN",
                   label_offset=-12))
    s.append(arrow(560, 130, 635, 130, label="/imu/data",
                   color=GREY, label_offset=-12))
    # CAN -> motors
    s.append(arrow(690, 260, 690, 280))
    s.append(arrow(820, 260, 820, 280))

    s.append(footer())
    write_svg("getting_started__intro__01.svg", "".join(s))


def d_intro_02_packages() -> None:
    """Three columns: shared, Lite-only, Prime-only — with arrows."""
    W, H = 920, 440
    s = [header(W, H)]
    s.append(title(20, 30, "Package organization",
                   sub="Shared core + per-robot leaves"))

    # Lanes
    s.append(group_box(20, 60, 290, 360, "Shared (Lite + Prime)"))
    s.append(group_box(330, 60, 280, 360, "Lite-only"))
    s.append(group_box(630, 60, 270, 360, "Prime-only"))

    def pkg(x, y, name, sub=None, fill=BLUE_FILL, stroke=BLUE):
        s.append(Box(x, y, 250, 44, name, sub=sub,
                     fill=fill, stroke=stroke).render())

    # Shared column
    pkg(40, 90, "humanoid_control_common", "RT helpers, MITState POD")
    pkg(40, 144, "humanoid_control_msgs", "MITCommand, ControlMode, ...")
    pkg(40, 198, "humanoid_controllers", "5 mode controllers + MIT traj")
    pkg(40, 252, "humanoid_control_policy", "ONNX runner + LeRobot ref")
    pkg(40, 306, "humanoid_drivers_socketcan", "SocketCAN bus library")

    # Lite column
    pkg(345, 110, "lite_description", "URDF + xacro + meshes",
        fill=GREEN_FILL, stroke=GREEN)
    pkg(345, 180, "humanoid_devices_robstride", "Robstride SystemInterface",
        fill=GREEN_FILL, stroke=GREEN)
    pkg(345, 250, "humanoid_bringup_lite", "launch + controllers YAML",
        fill=GREEN_FILL, stroke=GREEN)

    # Prime column
    pkg(645, 110, "humanoid_control_description_prime", "URDF + EtherCAT PDO",
        fill=RED_FILL, stroke=RED)
    pkg(645, 180, "humanoid_devices_sito", "Sito SystemInterface",
        fill=RED_FILL, stroke=RED)
    pkg(645, 250, "humanoid_bringup_prime", "+ ethercat.yaml",
        fill=RED_FILL, stroke=RED)

    # Arrows: humanoid_devices_robstride -> humanoid_drivers_socketcan
    s.append(arrow(345, 202, 290, 320, color=GREY))
    s.append(arrow(645, 202, 290, 320, color=GREY))
    # bringup_lite -> description_lite + hw_robstride + controllers + policy
    s.append(polyline([(345, 272), (310, 272), (310, 220), (290, 220)],
                      color=GREY))
    # legend
    s.append(text(640, 405, "Arrows = depends on", size=11,
                  anchor="end", fill=GREY))

    s.append(footer())
    write_svg("getting_started__intro__02.svg", "".join(s))


def d_hw_kinematic_tree() -> None:
    """Lite kinematic tree — chest at top, 3 sub-trees."""
    W, H = 1000, 540
    s = [header(W, H)]
    s.append(title(20, 30, "Lite kinematic tree",
                   sub="17 actuated joints (per-joint effort limit shown)"))

    # base_link / chest
    s.append(Box(420, 70, 160, 40, "base_link", fill=LIGHT, stroke=GREY).render())
    s.append(Box(420, 120, 160, 40, "chest", fill=LIGHT, stroke=GREY).render())
    s.append(arrow(500, 110, 500, 120, color=GREY))

    def joint(x, y, label, effort, side):
        color = BLUE
        fill = BLUE_FILL
        if side == "neck":
            color = GOLD
            fill = GOLD_FILL
        s.append(Box(x, y, 170, 36, label, sub=f"{effort} Nm",
                     fill=fill, stroke=color).render())

    # left arm (column 1)
    left = [
        ("left_shoulder_pitch", 17),
        ("left_shoulder_roll", 14),
        ("left_shoulder_yaw", 14),
        ("left_elbow_pitch", 14),
        ("left_wrist_yaw", 5.5),
        ("left_wrist_roll", 5.5),
        ("left_wrist_pitch", 5.5),
    ]
    for i, (n, e) in enumerate(left):
        joint(20, 180 + i * 48, n, e, "arm")
    # neck (column 2)
    neck = [("neck_yaw", 10), ("neck_roll", 10), ("neck_pitch", 10)]
    for i, (n, e) in enumerate(neck):
        joint(415, 220 + i * 60, n, e, "neck")
    # right arm (column 3)
    right = [
        ("right_shoulder_pitch", 17),
        ("right_shoulder_roll", 14),
        ("right_shoulder_yaw", 14),
        ("right_elbow_pitch", 14),
        ("right_wrist_yaw", 5.5),
        ("right_wrist_roll", 5.5),
        ("right_wrist_pitch", 5.5),
    ]
    for i, (n, e) in enumerate(right):
        joint(810, 180 + i * 48, n, e, "arm")

    # connect: chest -> first of each column
    s.append(polyline([(440, 160), (105, 175), (105, 180)], color=GREY))
    s.append(polyline([(500, 160), (500, 215), (500, 220)], color=GREY))
    s.append(polyline([(560, 160), (895, 175), (895, 180)], color=GREY))

    # chain arrows within each column
    for i in range(len(left) - 1):
        s.append(arrow(105, 180 + i * 48 + 36, 105, 180 + (i + 1) * 48,
                       color=GREY))
    for i in range(len(neck) - 1):
        s.append(arrow(500, 220 + i * 60 + 36, 500, 220 + (i + 1) * 60,
                       color=GREY))
    for i in range(len(right) - 1):
        s.append(arrow(895, 180 + i * 48 + 36, 895, 180 + (i + 1) * 48,
                       color=GREY))

    # legend
    s.append(Box(20, 480, 20, 16, "", fill=BLUE_FILL, stroke=BLUE,
                 radius=3).render())
    s.append(text(46, 488, "arm joint", size=11, anchor="start"))
    s.append(Box(140, 480, 20, 16, "", fill=GOLD_FILL, stroke=GOLD,
                 radius=3).render())
    s.append(text(166, 488, "neck joint", size=11, anchor="start"))

    s.append(footer())
    write_svg("reference__hardware_specs__01.svg", "".join(s))


def d_hw_can_layout() -> None:
    """Lite CAN-USB topology."""
    W, H = 900, 380
    s = [header(W, H)]
    s.append(title(20, 30, "Lite CAN topology",
                   sub="2 CAN-USB adapters, one per arm; neck shares can0"))

    s.append(Box(40, 80, 200, 60, "Onboard PC", sub="PREEMPT_RT",
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(300, 50, 140, 50, "CAN-USB #0",
                 fill=GREY_FILL, stroke=GREY).render())
    s.append(Box(300, 130, 140, 50, "CAN-USB #1",
                 fill=GREY_FILL, stroke=GREY).render())
    s.append(Box(490, 50, 100, 50, "can0",
                 fill=RED_FILL, stroke=RED).render())
    s.append(Box(490, 130, 100, 50, "can1",
                 fill=RED_FILL, stroke=RED).render())
    s.append(Box(640, 30, 240, 90,
                 ["7x Robstride", "left arm + 3x neck"],
                 fill=RED_FILL, stroke=RED).render())
    s.append(Box(640, 150, 240, 90,
                 ["7x Robstride", "right arm"],
                 fill=RED_FILL, stroke=RED).render())

    # USB lines (top)
    s.append(arrow(240, 100, 300, 75, color=GREY, label="USB",
                   label_offset=-10))
    s.append(arrow(240, 120, 300, 155, color=GREY, label="USB",
                   label_offset=-10))
    # CAN-USB -> can iface
    s.append(arrow(440, 75, 490, 75))
    s.append(arrow(440, 155, 490, 155))
    # can iface -> actuators
    s.append(arrow(590, 75, 640, 75, label="CAN @ 1 Mbit"))
    s.append(arrow(590, 155, 640, 155, label="CAN @ 1 Mbit"))

    s.append(text(450, 310,
                  "On real hardware the humanoid_devices_robstride plugin owns both buses; "
                  "from the controller's perspective the 17 joints are one flat list.",
                  size=11, anchor="middle", fill=GREY))

    s.append(footer())
    write_svg("reference__hardware_specs__02.svg", "".join(s))


def d_hw_mit_mode() -> None:
    """MIT-mode formula visual."""
    W, H = 920, 360
    s = [header(W, H)]
    s.append(title(20, 30, "MIT-mode hybrid command",
                   sub="Same five interfaces, same torque formula across silicon, sim, mock"))

    # 5 command interfaces (left)
    cmd_x = 30
    cmd_w = 200
    s.append(group_box(cmd_x, 70, cmd_w, 270, "5 cmd interfaces / joint"))
    cmds = [
        ("position", "q_cmd"),
        ("velocity", "qd_cmd"),
        ("effort", "tau_ff"),
        ("stiffness", "K_p"),
        ("damping", "K_d"),
    ]
    for i, (n, v) in enumerate(cmds):
        s.append(Box(cmd_x + 20, 100 + i * 45, cmd_w - 40, 32, n, sub=v,
                     fill=BLUE_FILL, stroke=BLUE).render())

    # Compute box (center)
    cx0, cw = 290, 320
    s.append(Box(cx0, 130, cw, 100,
                 ["tau = K_p * (q_cmd - q)",
                  "    + K_d * (qd_cmd - qd)",
                  "    + tau_ff"],
                 fill=GOLD_FILL, stroke=GOLD).render())
    s.append(text(cx0 + cw // 2, 250, "applied via mjData->qfrc_applied (sim)",
                  size=11, fill=GREY, anchor="middle"))
    s.append(text(cx0 + cw // 2, 268, "or motor firmware (real Robstride)",
                  size=11, fill=GREY, anchor="middle"))

    # 3 state interfaces (right)
    st_x = 660
    st_w = 200
    s.append(group_box(st_x, 110, st_w, 200, "3 state interfaces / joint"))
    states = [("position", "q"), ("velocity", "qd"), ("effort", "tau (meas)")]
    for i, (n, v) in enumerate(states):
        s.append(Box(st_x + 20, 140 + i * 55, st_w - 40, 36, n, sub=v,
                     fill=GREEN_FILL, stroke=GREEN).render())

    # Arrows
    s.append(arrow(cmd_x + cmd_w, 200, cx0, 180,
                   label="controller writes", label_offset=-10))
    s.append(arrow(cx0 + cw, 180, st_x, 200,
                   label="motor reads back", label_offset=-10))

    s.append(footer())
    write_svg("reference__hardware_specs__03.svg", "".join(s))


def d_sf_rt_cycle() -> None:
    """ros2_control RT cycle — vertical sequence with 3 phases."""
    W, H = 920, 540
    s = [header(W, H)]
    s.append(title(20, 30, "ros2_control real-time cycle (50 Hz)",
                   sub="One tick = read -> update -> write"))

    # 4 vertical lanes
    lanes = [
        ("controller_manager", 100, BLUE),
        ("Hardware plugin", 320, GREEN),
        ("Active controller", 540, GOLD),
        ("Bus (CAN / qfrc)", 770, RED),
    ]
    lane_top = 80
    lane_bot = 510
    for name, x, color in lanes:
        s.append(text(x, lane_top - 6, name, size=12, weight=600,
                      anchor="middle", fill=color))
        s.append(f'<line x1="{x}" y1="{lane_top}" x2="{x}" y2="{lane_bot}" '
                 f'stroke="{color}" stroke-width="1.4" stroke-dasharray="3 3"/>')

    # Phase backgrounds (horizontal bands)
    def phase(y, label, fill):
        s.append(f'<rect x="40" y="{y}" width="850" height="120" '
                 f'fill="{fill}" stroke="none"/>')
        s.append(text(880, y + 20, label, size=11, weight=700,
                      anchor="end", fill=GREY))

    phase(110, "read()", BLUE_FILL)
    phase(240, "update()", GOLD_FILL)
    phase(370, "write()", GREEN_FILL)

    # Arrows within each phase
    def msg(x1, y, x2, label, color=TEXT):
        s.append(arrow(x1, y, x2, y, color=color))
        mx = (x1 + x2) // 2
        s.append(label_pill(mx, y - 18, label))

    msg(100, 145, 320, "read(time, period)")
    s.append(arrow(320, 165, 770, 165, color=GREY, dashed=True))
    s.append(label_pill(550, 147, "poll cached state"))
    msg(770, 195, 320, "q, qd, tau")
    msg(320, 215, 100, "state_interfaces_")

    msg(100, 275, 540, "update(time, period)")
    s.append(text(540, 305,
                  "read state_interfaces_,",
                  size=11, fill=GREY, anchor="middle"))
    s.append(text(540, 322,
                  "compute, write command_interfaces_",
                  size=11, fill=GREY, anchor="middle"))
    msg(540, 345, 100, "return OK")

    msg(100, 405, 320, "write(time, period)")
    s.append(arrow(320, 435, 770, 435, color=GREY, dashed=True))
    s.append(label_pill(550, 417, "stage frames (lock-free)"))
    msg(770, 465, 320, "ack")
    msg(320, 485, 100, "return OK")

    s.append(footer())
    write_svg("concepts__architecture__01_rt_cycle.svg", "".join(s))


def d_sf_fsm() -> None:
    """Five control modes + flat joy_teleop switching."""
    W, H = 940, 480
    s = [header(W, H)]
    s.append(title(20, 28, "Five control modes",
                   sub="Each button → switch_controller directly; any "
                       "transition from any state (BEST_EFFORT)."))

    # joy_teleop hub (left).
    s.append(Box(45, 210, 185, 66,
                 ["joy_teleop", "/joy → switch_controller"],
                 fill=BLUE_FILL, stroke=BLUE).render())

    # Controller boxes (right), one per mode.
    def state(y, label, color, sub=None):
        fill = (GREEN_FILL if color == GREEN else
                GOLD_FILL if color == GOLD else
                BLUE_FILL if color == BLUE else LIGHT)
        s.append(Box(560, y, 250, 52, label, sub=sub, fill=fill,
                     stroke=color).render())
        return (560, y + 26)  # left-edge anchor

    zt = state(64, "zero_torque_controller", GREEN, sub="BACK = STOP")
    dp = state(142, "damping_controller", GREEN)
    sb = state(220, "standby_controller_a / b / y", BLUE)
    lo = state(298, "rl_policy_controller", GOLD, sub="LOCOMOTION")
    rm = state(376, "remote_policy_controller", GOLD, sub="REMOTE")

    # Fan-out edges from joy_teleop to each controller, labelled by button.
    hub = (230, 243)
    for (tx, ty), lbl in [(zt, "BACK"), (dp, "X"), (sb, "L1 + A / B / Y"),
                          (lo, "R1 + A"), (rm, "R1 + B")]:
        s.append(arrow(hub[0], hub[1], tx - 4, ty))
        s.append(label_pill((hub[0] + tx) // 2 + 20,
                            (hub[1] + ty) // 2 - 8, lbl))

    # Fault path note (native fallback, not a joy button). Short lines kept
    # left of the button pills (~x380).
    for i, line in enumerate([
            "Fault path (native, not a joy button):",
            "a controller update() → ERROR is dropped",
            "to damping via fallback_controllers.",
            "/safety_status is telemetry (no auto-DAMP)."]):
        s.append(text(46, 372 + i * 15, line, size=11, fill=GREY,
                      anchor="start"))

    # Legend (by role, not colour name), bottom-right, clear of the boxes.
    s.append(text(810, 444, "safe / fail-safe", size=11, anchor="end",
                  fill=GREEN))
    s.append(text(810, 459, "standby (interpolate to pose)", size=11,
                  anchor="end", fill=BLUE))
    s.append(text(810, 474, "active policy", size=11, anchor="end", fill=GOLD))

    s.append(footer())
    write_svg("concepts__five_mode_fsm__01.svg", "".join(s))


def d_sf_policy_tiers() -> None:
    """System 0 in-process policy execution + the System 1/2 ingress."""
    W, H = 960, 560
    s = [header(W, H)]
    s.append(title(24, 30, "Policy execution: System 0 (in-process, real-time)",
                   sub="Learned policies run in the RT loop; heavy deps confined to a launch-time prepare step"))

    # Launch-time prepare (non-RT, Python) -- top-left.
    s.append(group_box(24, 64, 300, 140, "Launch-time prepare (non-RT, Python)",
                       fill=GOLD_FILL, stroke=GOLD))
    s.append(Box(44, 104, 260, 80,
                 ["humanoid_control_policy / pianist_policy", "prepare"],
                 sub="resolve ONNX -> .mcap + overlay",
                 fill="white", stroke=GOLD).render())

    # System 0 controller (in-process, real-time) -- right, large.
    s.append(group_box(360, 64, 576, 252,
                       "System 0  -  RLPolicyController  (C++, real-time update())",
                       fill=BLUE_FILL, stroke=BLUE))
    om = Box(380, 104, 252, 58, "ObservationManager",
             sub="built-in + .mcap ref + extern", fill="white", stroke=BLUE)
    onx = Box(664, 104, 252, 58, "OnnxPolicy",
              sub="onnxruntime C++ (opt-in)", fill="white", stroke=BLUE)
    ref = Box(380, 184, 252, 58, "ReferenceProvider",
              sub="McapTracking / McapPiano", fill="white", stroke=BLUE)
    act = Box(664, 184, 252, 58, "ActionMapper",
              sub="decode + scatter -> full joints", fill="white", stroke=BLUE)
    for b in (om, onx, ref, act):
        s.append(b.render())
    s.append(arrow(ref.cx, ref.top, om.cx, om.bottom, color=BLUE))    # ref -> om
    s.append(arrow(om.right, om.cy, onx.left, onx.cy, color=BLUE))    # om  -> onnx
    s.append(arrow(onx.cx, onx.bottom, act.cx, act.top, color=BLUE))  # onnx -> act

    # prepare loads its artifacts into the controller, once, at launch.
    s.append(arrow(324, 134, 360, 134, color=GOLD, label="at launch"))

    # Per-tick inputs -- left, below prepare.
    inp = Box(24, 232, 320, 72, "Per-tick inputs",
              sub="state interfaces | /imu/data | /piano/key_state",
              fill=GREY_FILL, stroke=GREY)
    s.append(inp.render())
    s.append(arrow(inp.right, inp.cy, om.left, om.cy, color=GREY))

    # Output -- the five MIT command interfaces.
    out = Box(610, 392, 290, 52, "5 MIT command interfaces / joint",
              sub="K, D, q_cmd, qd_cmd, tau_ff -> bus", fill=LIGHT, stroke=GREY)
    s.append(out.render())
    s.append(arrow(act.cx, act.bottom, out.cx, out.top, color=BLUE, dashed=True))

    # System 1/2 ingress (non-RT, out-of-process) -- bottom-left.
    s.append(group_box(24, 344, 470, 150,
                       "System 1/2 ingress (non-RT, out-of-process)",
                       fill=GOLD_FILL, stroke=GOLD))
    ext = Box(44, 392, 180, 60, "External source",
              sub="gravity-comp / VLA", fill="white", stroke=GOLD)
    rpc = Box(300, 392, 174, 60, "RemotePolicyController",
              sub="C++", fill="white", stroke=GOLD)
    s.append(ext.render())
    s.append(rpc.render())
    s.append(arrow(ext.right, ext.cy, rpc.left, rpc.cy, color=GOLD,
                   label="MITCommand / DDS"))
    s.append(arrow(rpc.right, rpc.cy, out.left, out.cy, color=GOLD, dashed=True))

    s.append(text(out.cx, out.bottom + 20,
                  "one active at a time (FSM-selected)",
                  size=11, anchor="middle", fill=GREY))

    s.append(footer())
    write_svg("concepts__architecture__02_policy_tiers.svg", "".join(s))


def d_lite_mock_launch() -> None:
    """Mock-hardware bringup sequence."""
    W, H = 920, 540
    s = [header(W, H)]
    s.append(title(20, 30, "MuJoCo bringup spawn sequence",
                   sub="What happens when you run `ros2 launch humanoid_bringup_lite mujoco.launch.py`"))

    lanes = [
        ("launch", 100, GREY),
        ("xacro", 280, GREY),
        ("mujoco_sim", 460, BLUE),
        ("controller_manager", 640, BLUE),
        ("joy_teleop", 820, GOLD),
    ]
    lt, lb = 80, 510
    for name, x, color in lanes:
        s.append(text(x, lt - 6, name, size=12, weight=600,
                      anchor="middle", fill=color))
        s.append(f'<line x1="{x}" y1="{lt}" x2="{x}" y2="{lb}" '
                 f'stroke="{color}" stroke-width="1.4" stroke-dasharray="3 3"/>')

    def step(y, x1, x2, label, color=TEXT):
        s.append(arrow(x1, y, x2, y, color=color))
        mx = (x1 + x2) // 2
        s.append(label_pill(mx, y - 18, label))

    step(120, 100, 280, "expand xacro (use_sim:=true)")
    step(150, 280, 100, "URDF")
    step(180, 100, 460, "start mujoco_sim")
    step(210, 460, 640, "load MujocoRos2ControlPlugin")
    step(240, 640, 640,
         "register MujocoSystem (17 joints)", color=GREY)
    step(280, 100, 640, "spawn jsb (active)")
    step(310, 100, 640, "spawn zero_torque (active)")
    step(340, 100, 640, "spawn 4 others (inactive)")
    step(380, 100, 820, "start joy_teleop (waits for /joy)")

    s.append(text(W // 2, 460,
                  "System is now at ZERO_TORQUE (from the spawner), publishing "
                  "/joint_states at 50 Hz",
                  size=12, weight=600, fill=BLUE, anchor="middle"))

    s.append(footer())
    write_svg("getting_started__lite_101__01_mujoco_spawn.svg", "".join(s))


def d_lite_mujoco_internals() -> None:
    """mujoco_sim process internal architecture."""
    W, H = 880, 440
    s = [header(W, H)]
    s.append(title(20, 30, "MuJoCo bringup — single mujoco_sim process",
                   sub="Physics + controller_manager + hardware plugin all live in one binary"))

    # Big outer box
    s.append(group_box(40, 80, 800, 280,
                      "mujoco_sim process (mujoco_sim_ros2)",
                      fill="white"))

    s.append(Box(60, 130, 220, 60,
                 ["MuJoCo viewer", "(GLFW window)"],
                 fill=GOLD_FILL, stroke=GOLD).render())
    s.append(Box(60, 220, 220, 60,
                 ["Physics step", "(500 Hz)"],
                 fill=GOLD_FILL, stroke=GOLD).render())
    s.append(Box(330, 130, 230, 60,
                 ["MujocoRos2ControlPlugin", "(physics plugin)"],
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(330, 220, 230, 60,
                 ["controller_manager", "(50 Hz)"],
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(610, 175, 200, 60,
                 ["MujocoSystem", "(SystemInterface)"],
                 fill=GREEN_FILL, stroke=GREEN).render())

    s.append(arrow(280, 250, 330, 250))
    s.append(arrow(330, 160, 250, 160, color=GREY, dashed=True))  # viewer feedback
    s.append(arrow(440, 280, 440, 320, color=GREY))               # NOP
    s.append(arrow(560, 250, 610, 220))
    s.append(arrow(610, 195, 280, 245, color=GREY, dashed=True))  # qfrc_applied
    s.append(label_pill(440, 198, "qfrc_applied"))
    s.append(text(440, 305, "controllers loaded as usual via pluginlib",
                  size=11, fill=GREY, anchor="middle"))

    # External nodes
    s.append(Box(80, 380, 200, 40, "robot_state_publisher",
                 fill=LIGHT, stroke=GREY).render())
    s.append(Box(310, 380, 220, 40, "controller spawners",
                 fill=LIGHT, stroke=GREY).render())
    s.append(Box(560, 380, 180, 40, "joy_teleop",
                 fill=LIGHT, stroke=GREY).render())
    s.append(arrow(180, 380, 180, 290, color=GREY, dashed=True))
    s.append(label_pill(180, 340, "/robot_description"))
    s.append(arrow(420, 380, 420, 290, color=GREY, dashed=True))
    s.append(arrow(650, 380, 540, 290, color=GREY, dashed=True))
    s.append(label_pill(560, 345, "/clock from MuJoCo"))

    s.append(footer())
    write_svg("getting_started__lite_101__02_mujoco_internals.svg", "".join(s))


def d_xacro_3way() -> None:
    """xacro arg -> plugin selector decision tree."""
    W, H = 760, 400
    s = [header(W, H)]
    s.append(title(20, 30, "lite.urdf.xacro: 3-way hardware selector",
                   sub="One xacro file, three target backends"))

    s.append(Box(40, 100, 180, 60, "lite.urdf.xacro",
                 fill=BLUE_FILL, stroke=BLUE).render())

    # First branch: use_sim?
    s.append(Box(280, 70, 130, 40, "use_sim?",
                 fill=LIGHT, stroke=GREY).render())
    s.append(arrow(220, 130, 280, 90))
    s.append(label_pill(250, 110, "args"))

    # Yes -> MujocoSystem
    s.append(Box(470, 50, 250, 50, "mujoco_ros2_control/", sub="MujocoSystem",
                 fill=GOLD_FILL, stroke=GOLD).render())
    s.append(arrow(410, 80, 470, 75, label="true"))

    # No -> second branch
    s.append(Box(280, 200, 180, 40, "use_fake_hardware?",
                 fill=LIGHT, stroke=GREY).render())
    s.append(arrow(345, 110, 345, 200, label="false"))

    # Yes -> mock
    s.append(Box(490, 175, 230, 50,
                 "mock_components/GenericSystem",
                 fill=GREEN_FILL, stroke=GREEN).render())
    s.append(arrow(460, 215, 490, 200, label="true"))

    # No -> real
    s.append(Box(490, 280, 230, 60, "humanoid_devices_robstride/", sub="RobstrideSystem",
                 fill=RED_FILL, stroke=RED).render())
    s.append(arrow(370, 240, 490, 305, label="false"))

    s.append(text(380, 365,
                  "use_sim wins over use_fake_hardware when both are true",
                  size=11, fill=GREY, anchor="middle"))

    s.append(footer())
    write_svg("reference__packages__01_xacro_selector.svg", "".join(s))


def d_msgs_pubsub() -> None:
    """humanoid_control_msgs pub/sub topology."""
    W, H = 920, 480
    s = [header(W, H)]
    s.append(title(20, 30, "humanoid_control_msgs pub/sub topology",
                   sub="Who publishes / who subscribes for each active topic"))

    # 3 columns: publishers / topics / subscribers
    s.append(group_box(20, 70, 230, 380, "Publishers"))
    s.append(group_box(330, 70, 250, 380, "Topics"))
    s.append(group_box(660, 70, 240, 380, "Subscribers"))

    def pub(x, y, label, color=BLUE):
        fill = BLUE_FILL if color == BLUE else (
            GOLD_FILL if color == GOLD else
            GREEN_FILL if color == GREEN else
            RED_FILL if color == RED else LIGHT)
        s.append(Box(x, y, 200, 40, label, fill=fill, stroke=color).render())

    pub(35, 110, "StandbyController", BLUE)
    pub(35, 200, "Hardware plugins", RED)
    pub(35, 290, "policy source (ctrl / VLA)", BLUE)

    pub(350, 110, "/standby_controller/state", GREEN)
    pub(350, 200, "/safety_status", GREEN)
    pub(350, 290, "~/command (MITCommand)", GREEN)

    pub(680, 110, "(none - telemetry)", GREY)
    pub(680, 200, "(none - telemetry)", GREY)
    pub(680, 290, "RemotePolicyController", BLUE)

    # Arrows: publisher -> topic -> subscriber, one row each.
    for y in (130, 220, 310):
        s.append(arrow(235, y, 350, y, color=GREY))
        s.append(arrow(550, y, 680, y, color=GREY))

    s.append(text(W // 2, 462,
                  "ControlMode still ships in humanoid_control_msgs (DDS wire "
                  "bridge); /control_mode is no longer published.",
                  size=11, fill=GREY, anchor="middle"))
    s.append(text(W // 2, 476,
                  "Read the active mode from list_controllers. "
                  "/standby_controller/state and /safety_status are telemetry.",
                  size=11, fill=GREY, anchor="middle"))

    s.append(footer())
    write_svg("reference__messages__01.svg", "".join(s))


def d_arch_module_deps() -> None:
    """Module dependency graph — who builds against whom.

    Vertical: top layer is bringup (depends on everything below), bottom
    layer is the leaf libraries. Arrows point in the direction of
    dependency (A -> B reads as "A depends on B"). External deps live in
    a dotted box on the right; pluginlib-only edges are dashed to flag
    "loaded at runtime, not a build-time CMake dep".
    """
    W, H = 980, 620
    s = [header(W, H)]
    s.append(title(20, 30, "Module dependency graph",
                   sub="humanoid_control_* packages, build-time deps (solid) and pluginlib runtime deps (dashed)"))

    # Lane backgrounds (top -> bottom)
    s.append(group_box(40, 70, 720, 80, "Application / bringup"))
    s.append(group_box(40, 170, 720, 90, "Controllers + policies"))
    s.append(group_box(40, 280, 720, 90, "Hardware plugins + URDF"))
    s.append(group_box(40, 400, 720, 90, "Foundations (no humanoid_control_* deps)"))
    s.append(group_box(790, 70, 170, 420, "External", fill="#FAFAFA"))

    # Application / bringup
    s.append(Box(70, 95, 200, 40, "humanoid_bringup_lite", sub="launch + YAML",
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(310, 95, 200, 40, "humanoid_bringup_prime", sub="(scaffold)",
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(550, 95, 190, 40, "pianist_policy", sub="piano key-state",
                 fill=GOLD_FILL, stroke=GOLD).render())

    # Controllers + policies
    s.append(Box(70, 195, 200, 50, "humanoid_controllers",
                 sub="5 mode controllers + MIT traj",
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(310, 195, 200, 50, "humanoid_control_policy",
                 sub="ONNX runner (Python)",
                 fill=GOLD_FILL, stroke=GOLD).render())

    # Hardware plugins + description
    s.append(Box(70, 305, 200, 50, "humanoid_devices_robstride",
                 sub="RobstrideSystem",
                 fill=GREEN_FILL, stroke=GREEN).render())
    s.append(Box(310, 305, 200, 50, "humanoid_devices_sito",
                 sub="(stub)",
                 fill=GREEN_FILL, stroke=GREEN).render())
    s.append(Box(550, 305, 190, 50, "lite_description",
                 sub="URDF/xacro/MJCF",
                 fill=GREY_FILL, stroke=GREY).render())

    # Foundations
    s.append(Box(70, 425, 200, 50, "humanoid_drivers_socketcan",
                 sub="bus library + I/O thread",
                 fill=GREEN_FILL, stroke=GREEN).render())
    s.append(Box(310, 425, 200, 50, "humanoid_control_msgs",
                 sub="MITCommand, ControlMode, ...",
                 fill=GREY_FILL, stroke=GREY).render())
    s.append(Box(550, 425, 190, 50, "humanoid_control_common",
                 sub="MITState POD, RT helpers",
                 fill=GREY_FILL, stroke=GREY).render())

    # External column
    def ext(y, label):
        s.append(Box(810, y, 130, 36, label,
                     fill=LIGHT, stroke=GREY).render())
    ext(95, "ros2_control")
    ext(145, "rclcpp / rclpy")
    ext(195, "pluginlib")
    ext(245, "realtime_tools")
    ext(295, "mujoco_*_ros2")
    ext(345, "onnxruntime")
    ext(395, "huggingface_hub")
    ext(445, "nlohmann_json")

    # Edges (depends_on): from a box bottom to the dependee's top
    def dep(x1, y1, x2, y2, dashed=False, color=GREY):
        s.append(arrow(x1, y1, x2, y2, color=color, dashed=dashed))

    # bringup_lite -> controllers, policy, hw_robstride, description, msgs, common
    dep(170, 135, 170, 195)                    # -> controllers
    dep(190, 135, 360, 195)                    # -> policy
    dep(150, 135, 170, 305)                    # -> hw_robstride
    dep(210, 135, 600, 305)                    # -> description_lite
    dep(230, 135, 360, 425)                    # -> msgs (transitive but shown)
    # pianist_policy -> humanoid_control_msgs only
    dep(620, 135, 400, 425, color=GREY)
    # humanoid_control_policy -> humanoid_control_msgs + humanoid_control_common
    dep(380, 245, 380, 425)
    dep(420, 245, 620, 425, color=GREY)
    # humanoid_controllers -> humanoid_control_msgs + humanoid_control_common (and pluginlib loads them)
    dep(170, 245, 340, 425)
    dep(220, 245, 600, 425, color=GREY)
    # hw_robstride -> hw_socketcan + humanoid_control_msgs + humanoid_control_common
    dep(150, 355, 150, 425)
    dep(200, 355, 380, 425, color=GREY)
    dep(240, 355, 620, 425, color=GREY)
    # hw_sito -> hw_socketcan + humanoid_control_msgs
    dep(380, 355, 200, 425, color=GREY)
    dep(420, 355, 400, 425, color=GREY)

    # Pluginlib-only edges (dashed) — controllers load hw plugins at
    # runtime via controller_manager, not as a CMake dep.
    dep(120, 245, 110, 305, dashed=True, color=GOLD)
    s.append(label_pill(115, 280, "pluginlib", fill="white", stroke=GOLD))

    # Legend
    s.append(text(60, 525, "Solid arrow = build-time dep (CMake find_package + ament)",
                  size=11, anchor="start", fill=GREY))
    s.append(text(60, 545, "Dashed arrow = runtime dep only (pluginlib)",
                  size=11, anchor="start", fill=GREY))
    s.append(text(60, 570,
                  "Note: humanoid_controllers does NOT find_package(humanoid_devices_robstride) — "
                  "the plugin is loaded by controller_manager at launch.",
                  size=11, anchor="start", fill=GREY))

    s.append(footer())
    write_svg("concepts__architecture__03_module_deps.svg", "".join(s))


def d_arch_data_pipeline() -> None:
    """RT data pipeline — one tick, in detail.

    Two horizontal lanes (RT path + I/O thread), showing how a CAN frame
    becomes a controller observation and back. The dashed vertical line
    is the RT/non-RT boundary — everything that crosses it goes through
    a lock-free buffer.
    """
    W, H = 1020, 560
    s = [header(W, H)]
    s.append(title(20, 30, "RT data pipeline — one tick (read -> update -> write)",
                   sub="Where CAN frames live before they reach a controller, and how commands get back out"))

    # RT boundary line (vertical, at x = 540)
    s.append(f'<line x1="540" y1="60" x2="540" y2="500" stroke="{RED}" '
             f'stroke-width="2" stroke-dasharray="6 4"/>')
    s.append(text(540, 75, "RT boundary", size=11, weight=600,
                  anchor="middle", fill=RED))

    # Left half = bus (I/O thread, non-RT)
    s.append(group_box(40, 90, 470, 200, "I/O thread (non-RT, blocking syscalls OK)"))
    s.append(Box(60, 130, 130, 50, "kernel CAN", sub="can0 / can1",
                 fill=RED_FILL, stroke=RED).render())
    s.append(Box(220, 110, 130, 40, "epoll_wait",
                 fill=GREEN_FILL, stroke=GREEN).render())
    s.append(Box(220, 165, 130, 40, "decode frame",
                 fill=GREEN_FILL, stroke=GREEN).render())
    s.append(Box(220, 230, 130, 40, "encode frame",
                 fill=GREEN_FILL, stroke=GREEN).render())
    s.append(Box(380, 130, 120, 50,
                 ["RX ring", "(SPSC, 256)"],
                 fill=GOLD_FILL, stroke=GOLD).render())
    s.append(Box(380, 220, 120, 50,
                 ["TX ring", "(SPSC, 64)"],
                 fill=GOLD_FILL, stroke=GOLD).render())

    # I/O internal arrows
    s.append(arrow(190, 150, 220, 130, color=GREY))
    s.append(arrow(285, 150, 285, 165, color=GREY))
    s.append(arrow(350, 185, 380, 155, color=GREY))
    s.append(arrow(380, 245, 350, 250, color=GREY))
    s.append(arrow(285, 230, 285, 195, color=GREY))  # encode -> back to kernel via write()
    s.append(polyline([(220, 250), (140, 250), (140, 180)], color=GREY))
    s.append(label_pill(170, 250, "write()", fill="white"))

    # Right half = controller_manager (RT)
    s.append(group_box(560, 90, 440, 200, "controller_manager (RT, 50 Hz, no allocs)"))
    s.append(Box(580, 110, 170, 40, "RobstrideSystem.read",
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(580, 230, 170, 40, "RobstrideSystem.write",
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(790, 110, 190, 40, "state_interfaces", sub="q, qd, tau",
                 fill=LIGHT, stroke=GREY).render())
    s.append(Box(790, 230, 190, 40, "command_interfaces",
                 sub="q_cmd, qd_cmd, tau, K, D",
                 fill=LIGHT, stroke=GREY).render())
    s.append(Box(680, 170, 200, 40, "controller.update()",
                 fill=GOLD_FILL, stroke=GOLD).render())

    # RT internal arrows
    s.append(arrow(750, 130, 790, 130))
    s.append(arrow(790, 130, 780, 170))
    s.append(arrow(780, 210, 790, 230))
    s.append(arrow(790, 250, 750, 250))

    # Cross-boundary arrows (RT <-> I/O via rings)
    s.append(arrow(500, 155, 580, 130, label="lock-free pop", label_offset=-12))
    s.append(arrow(580, 250, 500, 245, label="lock-free push", label_offset=12))

    # Joint frame transform happens in read/write
    s.append(text(660, 100, "calibration applied here",
                  size=10, anchor="middle", fill=GREY))
    s.append(text(660, 290, "calibration applied here",
                  size=10, anchor="middle", fill=GREY))

    # Notes
    s.append(text(W // 2, 360,
                  "The I/O thread is the only place that touches the kernel CAN socket. "
                  "Lock-free SPSC rings cross the RT boundary in both directions.",
                  size=12, weight=600, fill=BLUE, anchor="middle"))
    s.append(text(W // 2, 385,
                  "Calibration (direction, homing_offset) is applied inside read()/write() so "
                  "controllers see joint frame, never the raw encoder.",
                  size=11, fill=GREY, anchor="middle"))

    # Timing notes
    s.append(group_box(40, 430, 470, 90, "Timing", fill=BLUE_FILL))
    s.append(text(60, 460, "I/O thread:", size=11, weight=600, fill=BLUE, anchor="start"))
    s.append(text(150, 460, "syscall-blocked on epoll_wait; drains kernel at line rate.",
                  size=11, anchor="start"))
    s.append(text(60, 482, "RT thread:", size=11, weight=600, fill=BLUE, anchor="start"))
    s.append(text(150, 482, "20 ms tick. read() = pop ring head, no syscalls.",
                  size=11, anchor="start"))
    s.append(text(60, 504, "Latency:", size=11, weight=600, fill=BLUE, anchor="start"))
    s.append(text(150, 504, "~1 ms wire-to-controller best case; tail bounded by SPSC depth.",
                  size=11, anchor="start"))

    s.append(group_box(560, 430, 440, 90, "If a buffer fills up", fill=RED_FILL))
    s.append(text(580, 460, "RX ring overflow:", size=11, weight=600, fill=RED, anchor="start"))
    s.append(text(720, 460, "oldest frame dropped (latest-wins).",
                  size=11, anchor="start"))
    s.append(text(580, 482, "TX ring overflow:", size=11, weight=600, fill=RED, anchor="start"))
    s.append(text(720, 482, "write_command() returns false; flag TX_QUEUE_OVERRUN.",
                  size=11, anchor="start"))
    s.append(text(580, 504, "Net effect:", size=11, weight=600, fill=RED, anchor="start"))
    s.append(text(720, 504, "stale state propagates -> SafetyStatus -> auto-DAMP.",
                  size=11, anchor="start"))

    s.append(footer())
    write_svg("concepts__architecture__04_data_pipeline.svg", "".join(s))


def d_calibration_flow() -> None:
    """Calibration math at the bus boundary."""
    W, H = 1000, 480
    s = [header(W, H)]
    s.append(title(20, 30, "Calibration: joint frame ⇄ motor frame",
                   sub="Applied at the bus boundary in RobstrideSystem::read / ::write"))

    # Top row: read path
    s.append(group_box(40, 70, 920, 150, "read() — motor frame → joint frame"))
    s.append(Box(70, 105, 170, 60,
                 ["raw_motor_pos", "(rad, encoder)"],
                 fill=RED_FILL, stroke=RED).render())
    s.append(Box(290, 105, 240, 60,
                 ["direction * (raw - homing_offset)"],
                 fill=GOLD_FILL, stroke=GOLD).render())
    s.append(Box(580, 105, 170, 60,
                 ["joint_pos", "(rad, URDF frame)"],
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(800, 105, 140, 60,
                 ["state_interface", "<joint>/position"],
                 fill=LIGHT, stroke=GREY).render())
    s.append(arrow(240, 135, 290, 135))
    s.append(arrow(530, 135, 580, 135))
    s.append(arrow(750, 135, 800, 135))
    s.append(text(580, 185, "qd and tau use the same direction, NO offset (derivatives).",
                  size=11, anchor="middle", fill=GREY))

    # Bottom row: write path (inverse)
    s.append(group_box(40, 240, 920, 150, "write() — joint frame → motor frame"))
    s.append(Box(70, 275, 170, 60,
                 ["command_interface", "<joint>/position"],
                 fill=LIGHT, stroke=GREY).render())
    s.append(Box(290, 275, 240, 60,
                 ["direction * joint + homing_offset"],
                 fill=GOLD_FILL, stroke=GOLD).render())
    s.append(Box(580, 275, 170, 60,
                 ["raw_motor_cmd"],
                 fill=RED_FILL, stroke=RED).render())
    s.append(Box(800, 275, 140, 60,
                 ["CAN frame", "(MIT-mode)"],
                 fill=RED_FILL, stroke=RED).render())
    s.append(arrow(240, 305, 290, 305))
    s.append(arrow(530, 305, 580, 305))
    s.append(arrow(750, 305, 800, 305))

    # Constants: where they live
    s.append(text(60, 420, "Constants per joint:",
                  size=12, weight=600, anchor="start", fill=TEXT))
    s.append(Box(220, 405, 230, 36, "direction (URDF)",
                 sub="wiring fact, same per robot model",
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(470, 405, 250, 36, "homing_offset (calibration.json)",
                 sub="per physical robot, regenerated",
                 fill=GOLD_FILL, stroke=GOLD).render())

    s.append(footer())
    write_svg("concepts__calibration_math__01.svg", "".join(s))


def d_safety_pipeline() -> None:
    """Safety pipeline — fault to DAMPING in one tick."""
    W, H = 1000, 500
    s = [header(W, H)]
    s.append(title(20, 30, "Safety pipeline — detection, telemetry, native fallback",
                   sub="Detection (plugin) → telemetry (latched topic) → operator + fallback_controllers"))

    # Three layers, left to right
    s.append(group_box(40, 70, 280, 380, "Layer 1: detection (plugin)"))
    s.append(group_box(360, 70, 240, 380, "Layer 2: telemetry"))
    s.append(group_box(640, 70, 320, 380, "Layer 3: native fallback + operator"))

    # Fault sources (left column)
    def fault(y, name, src):
        s.append(Box(60, y, 240, 40, name, sub=src,
                     fill=RED_FILL, stroke=RED).render())

    fault(100, "BUS_OFF", "socket open / ENETDOWN (sticky)")
    fault(150, "RX_TIMEOUT", "joint silent > rx_timeout_ms")
    fault(200, "TX_QUEUE_OVERRUN", "outbound SPSC ring full")
    fault(250, "MOTOR_FAULT", "OperationStatus.fault_bits")
    fault(300, "TEMPERATURE_LIMIT", "decoded from same frame")
    fault(350, "INVALID_FRAME", "DLC / comm-type mismatch")
    s.append(text(180, 405, "(per-tick rebuild from current state, not history)",
                  size=10, anchor="middle", fill=GREY))

    # Level derivation (middle column)
    s.append(Box(380, 110, 200, 40, "SafetyStatus", sub="humanoid_control_msgs",
                 fill=GREY_FILL, stroke=GREY).render())
    s.append(Box(380, 170, 200, 40, "level: OK / WARN / FAULT / CRITICAL",
                 fill=GREY_FILL, stroke=GREY).render())
    s.append(Box(380, 230, 200, 40, "flags: uint32 bit mask",
                 fill=GREY_FILL, stroke=GREY).render())
    s.append(Box(380, 290, 200, 40, "source: 'humanoid_devices_robstride/can0'",
                 fill=GREY_FILL, stroke=GREY).render())
    s.append(Box(380, 360, 200, 50,
                 ["/safety_status", "(TRANSIENT_LOCAL)"],
                 fill=GOLD_FILL, stroke=GOLD).render())
    s.append(arrow(480, 270, 480, 290, color=GREY))
    s.append(arrow(480, 330, 480, 360, color=GREY))

    # Response (right column): /safety_status is telemetry (no auto-DAMP);
    # the automatic path is native fallback_controllers on a controller error.
    s.append(Box(660, 100, 280, 44,
                 ["/safety_status = telemetry", "rqt / logs / operator"],
                 fill=GREY_FILL, stroke=GREY).render())
    s.append(text(800, 168, "No auto-DAMP node — the operator reacts",
                  size=11, anchor="middle", fill=GREY))
    s.append(text(800, 183, "(BACK = STOP / X = DAMP).",
                  size=11, anchor="middle", fill=GREY))

    s.append(Box(660, 210, 280, 44,
                 ["controller update() → ERROR", "(e.g. non-finite obs)"],
                 fill=RED_FILL, stroke=RED).render())
    s.append(Box(660, 282, 280, 38, "controller_manager: fallback_controllers",
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(Box(660, 340, 280, 34, "damping_controller",
                 fill=GOLD_FILL, stroke=GOLD).render())
    s.append(Box(660, 392, 280, 34, "zero_torque_controller",
                 fill=GREEN_FILL, stroke=GREEN).render())
    s.append(arrow(800, 254, 800, 282))
    s.append(arrow(800, 320, 800, 340, label="activate", label_offset=8))
    s.append(arrow(800, 374, 800, 392, label="its fallback", label_offset=8))

    # Cross-column arrows
    s.append(arrow(300, 250, 380, 200, label="aggregate", label_offset=-12))
    s.append(arrow(580, 385, 660, 122, label="publish", label_offset=-12))

    # Note
    s.append(text(W // 2, 466,
                  "The automatic path is native fallback_controllers (controller "
                  "ERROR → damping → zero_torque), independent of /safety_status.",
                  size=11, anchor="middle", fill=GREY))
    s.append(text(W // 2, 482,
                  "BUS_OFF is a sticky flag cleared only on the next on_activate().",
                  size=11, anchor="middle", fill=GREY))

    s.append(footer())
    write_svg("concepts__safety_pipeline__01.svg", "".join(s))


def d_piano_data_flow() -> None:
    """Piano-task data flow: .npz to MITCommand."""
    W, H = 1040, 460
    s = [header(W, H)]
    s.append(title(20, 30, "Piano-task data flow",
                   sub=".npz on disk → MIDI replay → policy observation → joint command"))

    # Single horizontal pipeline with annotated boundaries
    boxes = [
        (40,  130, 150, 70,
         ["song.npz", "(Pianist)"], GREY_FILL, GREY),
        (220, 130, 160, 70,
         ["MusicSequence", "(numpy bool[F,K])"], GREEN_FILL, GREEN),
        (410, 130, 170, 70,
         ["pianist_policy", "song replay"], BLUE_FILL, BLUE),
        (610, 130, 200, 70,
         ["/piano/key_command", "TRANSIENT_LOCAL"], GOLD_FILL, GOLD),
        (840, 130, 180, 70,
         ["PianoKeyReference", "Provider"], BLUE_FILL, BLUE),
    ]
    for x, y, w, h, label, fill, stroke in boxes:
        s.append(Box(x, y, w, h, label, fill=fill, stroke=stroke).render())

    # Second row
    boxes2 = [
        (220, 280, 200, 60,
         ["ObservationManager", "(rclpy)"], GOLD_FILL, GOLD),
        (470, 280, 180, 60,
         ["OnnxPolicyRunner", "(meta-driven)"], GOLD_FILL, GOLD),
        (700, 280, 180, 60,
         ["PolicyActionDecoder", "+ ActionMapper"], GOLD_FILL, GOLD),
        (920, 280, 100, 60,
         ["MITCommand"], BLUE_FILL, BLUE),
    ]
    for x, y, w, h, label, fill, stroke in boxes2:
        s.append(Box(x, y, w, h, label, fill=fill, stroke=stroke).render())

    # Top row arrows
    for i in range(len(boxes) - 1):
        x1 = boxes[i][0] + boxes[i][2]
        x2 = boxes[i + 1][0]
        s.append(arrow(x1, 165, x2, 165))
    s.append(label_pill(195, 150, "load"))
    s.append(label_pill(395, 150, "timer"))
    s.append(label_pill(593, 150, "publish"))
    s.append(label_pill(820, 150, "subscribe"))

    # Provider -> observation manager (down + left)
    s.append(polyline([(930, 200), (930, 240), (320, 240), (320, 280)]))
    s.append(label_pill(620, 240, "key_goal_states + lookahead"))

    # Second row arrows
    for i in range(len(boxes2) - 1):
        x1 = boxes2[i][0] + boxes2[i][2]
        x2 = boxes2[i + 1][0]
        s.append(arrow(x1, 310, x2, 310))
    s.append(label_pill(445, 295, "obs vec"))
    s.append(label_pill(675, 295, "action"))
    s.append(label_pill(900, 295, "joints"))

    # MITCommand -> RemotePolicyController
    s.append(Box(870, 380, 150, 50,
                 ["Remote", "PolicyController"],
                 fill=BLUE_FILL, stroke=BLUE).render())
    s.append(arrow(970, 340, 945, 380, label="DDS"))

    # Notes
    s.append(text(W // 2, 80,
                  "Latched QoS lets a late-spawning policy runner pick up the most recent goal — no startup race.",
                  size=11, anchor="middle", fill=GREY))

    s.append(footer())
    write_svg("concepts__architecture__05_piano_data_flow.svg", "".join(s))


def d_frozen_schemas() -> None:
    """Frozen schemas — what's locked once a policy ships."""
    W, H = 920, 480
    s = [header(W, H)]
    s.append(title(20, 30, "Frozen schemas",
                   sub="Changing these requires retraining every policy that depends on them"))

    # Two columns: schema name | consumers (who breaks if changed)
    s.append(group_box(40, 70, 380, 380, "Schema"))
    s.append(group_box(460, 70, 420, 380, "Who locks in when you ship"))

    rows = [
        ("humanoid_control_msgs/MITCommand",
         "fields name + order",
         ["RemotePolicyController (subscriber)",
          "humanoid_control_policy.ActionMapper (publisher)",
          "every trained ONNX (action_joint_names)"]),
        ("Joint order in YAML",
         "controllers.yaml `joints:` list",
         ["RLPolicyController obs index",
          "ObservationManager term layout",
          "URDF `<ros2_control>` block order"]),
        ("MITState (POD + dataclass)",
         "field names, types, units",
         ["C++ controllers (read state_interfaces)",
          "Python ObservationManager (mirror)",
          "trained policy observation_term_names"]),
        ("ObservationTerm.scale / default",
         "per-joint, per-term constants",
         ["every ONNX trained against this scale",
          "regression would require recalibration"]),
    ]

    yh = 90
    for name, sub, who in rows:
        s.append(Box(60, yh, 340, 70, name, sub=sub,
                     fill=BLUE_FILL, stroke=BLUE).render())
        for i, w in enumerate(who):
            s.append(text(490, yh + 20 + i * 18, w, size=11, anchor="start"))
        yh += 90

    s.append(text(60, 470,
                  "Edits to anything in the left column = a new ONNX export + a sim2real re-verification pass.",
                  size=11, anchor="start", fill=GREY))

    s.append(footer())
    write_svg("concepts__frozen_schemas__01.svg", "".join(s))


def d_real_bringup_spawn() -> None:
    """real.launch.py spawn sequence on Lite hardware."""
    W, H = 980, 580
    s = [header(W, H)]
    s.append(title(20, 30, "Lite real-hardware bringup",
                   sub="What happens between `pixi run launch-real` and `ZERO_TORQUE active`"))

    lanes = [
        ("operator", 80, GREY),
        ("launch", 240, GREY),
        ("ros2_control_node", 420, BLUE),
        ("RobstrideSystem", 600, GREEN),
        ("joy_teleop", 780, GOLD),
    ]
    lt, lb = 70, 550
    for name, x, color in lanes:
        s.append(text(x, lt - 6, name, size=12, weight=600,
                      anchor="middle", fill=color))
        s.append(f'<line x1="{x}" y1="{lt}" x2="{x}" y2="{lb}" '
                 f'stroke="{color}" stroke-width="1.4" stroke-dasharray="3 3"/>')

    def step(y, x1, x2, label, color=TEXT):
        s.append(arrow(x1, y, x2, y, color=color))
        mx = (x1 + x2) // 2
        s.append(label_pill(mx, y - 18, label))

    step(110, 80, 240, "pixi run launch-real")
    step(140, 240, 80, "(can interfaces UP?)", color=GREY)
    step(170, 80, 80, "ip link set can0/1 up @ 1Mbit", color=GREY)
    step(210, 240, 420, "spawn ros2_control_node")
    step(240, 420, 600, "load RobstrideSystem (pluginlib)")
    step(270, 600, 600, "open can0 + can1 sockets")
    step(300, 600, 600, "load calibration.json")
    step(330, 600, 600, "I/O threads up (epoll)")
    step(360, 240, 420, "spawn joint_state_broadcaster (active)")
    step(390, 240, 420, "spawn zero_torque (active)")
    step(420, 240, 420, "spawn damping/standby/rl/remote (inactive)")
    step(460, 240, 780, "start joy_teleop (reads /joy)")
    step(490, 780, 420, "switch_controller on button press", color=GREY)

    s.append(text(W // 2, 565,
                  "After this sequence: motors compliant, /joint_states @ 50 Hz, at ZERO_TORQUE (from the spawner).",
                  size=12, weight=600, fill=BLUE, anchor="middle"))

    s.append(footer())
    write_svg("how_to__first_real_bringup__01.svg", "".join(s))


# --- Main --------------------------------------------------------------------

def main() -> None:
    print(f"Generating SVGs into {OUT.relative_to(ROOT)}/")
    # Getting started
    d_intro_01_system()
    d_intro_02_packages()
    d_lite_mock_launch()           # writes getting_started__lite_101__01_mujoco_spawn.svg
    d_lite_mujoco_internals()      # writes getting_started__lite_101__02_mujoco_internals.svg
    # Concepts
    d_sf_rt_cycle()                # writes concepts__architecture__01_rt_cycle.svg
    d_sf_policy_tiers()            # writes concepts__architecture__02_policy_tiers.svg
    d_arch_module_deps()
    d_arch_data_pipeline()
    d_piano_data_flow()            # writes concepts__architecture__05_piano_data_flow.svg
    d_sf_fsm()                     # writes concepts__five_mode_fsm__01.svg
    d_calibration_flow()
    d_safety_pipeline()
    d_frozen_schemas()
    # Reference
    d_hw_kinematic_tree()          # writes reference__hardware_specs__01.svg
    d_hw_can_layout()              # writes reference__hardware_specs__02.svg
    d_hw_mit_mode()                # writes reference__hardware_specs__03.svg
    d_xacro_3way()                 # writes reference__packages__01_xacro_selector.svg
    d_msgs_pubsub()
    # How-to
    d_real_bringup_spawn()
    print("Done.")


if __name__ == "__main__":
    main()
