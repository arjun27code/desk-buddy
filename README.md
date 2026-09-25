# Desk Buddy

Phone-first Desk Buddy powered by Termux.

The default version now uses a native Android pixel surface through Termux:GUI. It is not a website and does not use localhost or a browser.

## Why the renderer changed

A terminal is built from character cells. That is fine for proving the behavior loop, but it cannot produce genuinely smooth RoboEyes-style curves.

The default renderer now uses a shared pixel buffer through Termux:GUI so the face can be drawn like an OLED robot display.

## Native face behavior

- bright rounded cyan RoboEyes-style eyes
- no giant rectangular pupils
- soft cyan glow
- smooth whole-eye idle movement
- touch-follow gaze
- natural auto blinking
- occasional double blink
- happy laugh/bounce
- curious upper-corner gaze
- annoyed angular eyelids plus horizontal flicker
- sad/tired downward gaze
- emotions auto-return to idle after 2.5 seconds
- tap the face to cycle:
  happy -> curious -> annoyed -> sad

The behavior is based on the same ideas used by FluxGarage RoboEyes: configurable rounded eye geometry, auto-blinking, idle repositioning, curiosity, moods and one-shot expression animation.

## Requirements

1. Termux
2. Python
3. Termux:GUI Android plugin
4. Python binding: termuxgui

Important: Termux and Termux:GUI must come from the same installation source because Termux plugins must use matching signatures.

## Existing clone update

    cd ~/desk-buddy
    git pull origin main
    bash install.sh

Then launch:

    desk-buddy

The first native run requires the Termux:GUI Android plugin to already be installed.

## Controls

Native pixel mode:

- touch and drag: the eyes follow your finger
- quick tap: cycle happy -> curious -> annoyed -> sad
- Android Back: close the Desk Buddy activity

Terminal fallback:

    desk-buddy --terminal

The terminal version remains only as a compatibility fallback.

## Files

    gui_buddy.py     native Termux:GUI pixel renderer
    desk_buddy.py    old terminal fallback
    start.sh         launcher
    install.sh       installer

## Next upgrades

After the native renderer is stable on the phone:

1. weather card animation without cluttering the face
2. charging expression
3. low-battery tired expression
4. notification reactions
5. proximity / motion reactions through Termux:API
6. optional sounds
