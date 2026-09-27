# Desk Buddy

Phone-first native Desk Buddy for Termux + Termux:GUI.

It runs directly on the Android phone screen. No browser, localhost page, front-camera feed, or OpenCV vision pipeline is used.

## Cosmo-style eyes

The default eyes now adapt the visual geometry and core expression behavior from:

- TheDeveloperOps/rant-engineer-projects
- IOT/CosmoEyesKeyChainProject.md

Source:
https://github.com/TheDeveloperOps/rant-engineer-projects/blob/main/IOT/CosmoEyesKeyChainProject.md

The source document explicitly states that it is free to use, modify and share for personal or educational projects.

The phone renderer keeps the same core 128x64 eye geometry used by that project:

- eye width: 34
- eye height: 40
- corner radius: 10
- gap: 12
- left eye X: 24
- right eye X: 70
- eye Y: 12

Core modes adapted from the source:

- Normal / Idle
- Happy
- Surprised
- Angry
- Sleepy
- Wink
- Love / heart eyes
- Look Left
- Look Right

The source ESP32 sketch uses very fast OLED frame steps. Desk Buddy preserves the geometry and behavior while stretching the fastest transitions just enough to remain visible at the phone renderer's 30 FPS refresh rate.

Normal mode follows the same personality pattern:

- frequent blink
- short left glance
- short right glance
- short upward glance
- return to center

The original phone project features remain around the Cosmo eye renderer:

- device tilt
- shake reactions
- autonomous scenes
- weather
- sleep scene
- captions
- local gibber/data-chirp voice
- Game Hub

## Sleep / wake

The source Cosmo project uses a roughly one-second BOOT-button hold to enter light sleep.

On the phone version:

- hold the face for about 1 second: sleep
- tap while sleeping: wake
- strong shake while sleeping: wake

The existing full-screen Desk Buddy sleep scene remains active, including bed, moon, stars and animated Z marks.

## Game Hub

Double-tap Desk Buddy to open the native Game Hub.

Games:

### Tic-Tac-Toe

- you play X
- Desk Buddy plays O
- local minimax opponent
- tap a square to play

### Pong

- user paddle at the bottom
- Desk Buddy paddle at the top
- drag horizontally
- first to five

### Snake

- swipe up/down/left/right
- collect yellow food
- collision ends the round

### OLED Show

Plays the local 128x64 bitmap animation asset.

Supported files:

    animation_frames.h
    animation_frames(1).h

Optional timing sketch:

    loveMeNotOledLyrics.ino
    loveMeNotOledLyrics(1).ino

## Camera removed

Desk Buddy no longer requests or uses camera access.

Removed from the active project:

- front-camera preview
- face tracking
- hand/finger detection
- OpenCV camera analysis
- camera gesture diagnostics

The old camera modules were deleted from the repository and the installer no longer installs OpenCV for Desk Buddy.

Android may still remember an old camera permission previously granted to Termux:API. Desk Buddy does not use it anymore and it can be revoked manually from Android App Info.

## Current character system

Desk Buddy includes:

- Cosmo-style 128x64 eye geometry
- auto blink and short idle glances
- touch/drag gaze
- autonomous moods
- shake-triggered Dizzy reaction
- accelerometer + gyroscope tilt
- bike scene
- car scene
- walk scene
- park scene
- screen-edge peek
- full-screen rain
- lightning
- sunny scene
- night scene
- rainbow
- full sleep scene
- gibber/data-chirp voice
- real-text captions
- native clock/status UI

The renderer is tuned for phone hardware at roughly 30 FPS with a reduced native pixel buffer.

## Controls

Normal Buddy:

- drag: eyes follow your finger
- single tap: cycle expressions
- double-tap: open Game Hub
- hold about 1 second: sleep
- tap while sleeping: wake
- tilt phone: eyes react to device tilt
- shake phone: Dizzy / wake reaction

Game Hub:

- tap a tile to launch it
- top-left corner: back / exit
- controls depend on the selected game

## Requirements

1. Termux
2. Termux:GUI Android plugin
3. Termux:API Android plugin
4. Python
5. termuxgui Python package
6. termux-api Termux package

Install Termux and its plugins from the same source so their Android signatures match.

## Install / update

    cd ~/desk-buddy
    git pull origin main
    bash install.sh

The installer now runs:

- Python syntax checks
- Cosmo eye geometry self-test
- Game Hub logic self-test

Expected lines include:

    Cosmo eyes self-test: PASS
    Game Hub self-test: PASS

Run:

    desk-buddy

Keep the phone reasonably still for the first couple of seconds while motion sensors calibrate.

## Diagnostics

List sensors:

    termux-sensor -l

Test motion sensors:

    termux-sensor -s Accelerometer,Gyroscope -d 100 -n 10

Test OLED animation directly:

    desk-buddy --test-oled

Terminal fallback:

    desk-buddy --terminal

## Main files

    gui_buddy.py       native renderer, character and runtime
    cosmo_eyes.py      source-matched Cosmo eye geometry and expressions
    buddy_advanced.py  scenes, weather, sleep and motion fusion
    game_hub.py        Tic-Tac-Toe, Pong, Snake and game menu
    gibber_voice.py    local data-chirp voice + captions
    oled_asset_show.py local OLED frame player
    desk_buddy.py      terminal fallback
    start.sh           launcher
    install.sh         installer

## Attribution

Cosmo eye geometry and the core Normal / Happy / Surprised / Angry / Sleepy / Wink / Love / Look Left / Look Right behavior are adapted from:

TheDeveloperOps/rant-engineer-projects — IOT/CosmoEyesKeyChainProject.md

https://github.com/TheDeveloperOps/rant-engineer-projects/blob/main/IOT/CosmoEyesKeyChainProject.md

The original source document states: free to use, modify and share for personal or educational projects.

The ESP32 WiFi access-point/browser-control implementation itself is not required by this phone-native version, so that hardware/network stack was not ported. Desk Buddy uses native touch controls instead.
