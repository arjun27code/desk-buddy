# Desk Buddy

Phone-first native Desk Buddy for Termux + Termux:GUI.

It runs directly on the Android phone screen. No browser, localhost page, camera feed, or OpenCV vision pipeline is used.

## Current character

Desk Buddy has a RoboEyes-inspired face with:

- smooth eye movement and auto-blink
- touch/drag gaze
- random idle gaze
- expressive moods
- autonomous scenes
- full-screen rain, lightning, sunny, moon/stars and rainbow scenes
- bike, car, walking, park and screen-edge peek scenes
- sleep mode with a tiny bed, moon, stars and animated Z marks
- accelerometer + gyroscope tilt
- shake reactions and shake-to-wake
- local gibber/data-chirp voice with real-text captions
- local clock and native status overlay

The renderer is tuned for phone hardware at roughly 30 FPS with a reduced native pixel buffer.

## Camera removed

Desk Buddy no longer requests or uses camera access.

Removed from the active project:

- front-camera preview
- face tracking
- hand/finger detection
- OpenCV camera analysis
- camera gesture diagnostics

The old camera modules were deleted from the repository and the installer no longer installs OpenCV for Desk Buddy.

Android may still remember a camera permission previously granted to the Termux:API app. That permission is not used by this project anymore. It can be revoked manually from Android App Info if desired.

## Game Hub

Desk Buddy can now play games with you directly on the native screen.

Open Game Hub with either:

- double-tap on Desk Buddy
- long-press on Desk Buddy

Game Hub contains four tiles:

### Tic-Tac-Toe

Top-left tile.

- you play X
- Desk Buddy plays O
- Buddy uses a small local minimax opponent
- tap a square to play
- tap the top-left back corner to return to Game Hub

### Pong

Top-right tile.

- your paddle is at the bottom
- Desk Buddy controls the top paddle
- drag horizontally to move
- first to five wins
- Buddy's paddle has limited speed so the game is playable

### Snake

Bottom-left tile.

- swipe up/down/left/right
- eat the yellow targets
- collision ends the round
- tap after game-over to restart

### OLED Show

Bottom-right tile.

This plays the local 128x64 OLED animation asset already used by the project.

Supported frame filenames:

    animation_frames.h
    animation_frames(1).h

Optional timing sketch:

    loveMeNotOledLyrics.ino
    loveMeNotOledLyrics(1).ino

The files may be in the project folder or the phone Downloads folder.

Direct playback diagnostic:

    desk-buddy --test-oled

## Interaction design

The interface now has an original compact hardware-console treatment:

- subtle chassis corner brackets
- tiny status lamps
- bottom touch rail
- cyan/black electronics aesthetic
- full-screen game cards and game surfaces

This takes inspiration from the general idea of a small TFT-based physical desk companion while keeping the phone UI original.

## ARNAB9669/Desk-Buddy study

The external `ARNAB9669/Desk-Buddy` repository was reviewed before this update.

Its current source implements:

- ESP32 Wi-Fi + WebSocket connection
- INMP441 microphone capture
- TTP223 touch input
- double-tap interaction
- a FastAPI WebSocket server
- Gemini audio processing
- gTTS response generation
- hardware files for a 1.8-inch TFT desk robot, servos, speaker/amplifier, PCB and 3D enclosure

Important: the repository's current `robo.cpp` does **not** contain game logic, and its current code does not implement the TFT face/game UI shown as a software feature. The games in this project are therefore original phone-side implementations, not copied from that repository.

The external repository also has no visible LICENSE file in its root at the time it was reviewed, so its source/CAD/assets were not copied into this project. Only general interaction ideas such as double-tap and a compact hardware-console feel were reimplemented independently.

## Controls

Normal Buddy:

- drag: eyes follow your finger
- single tap: cycle emotion
- double-tap: open Game Hub
- long-press: open Game Hub
- tilt phone: face reacts to device tilt
- shake phone: Dizzy / wake reaction

Game Hub:

- tap a game tile to launch it
- top-left screen corner: back / exit
- controls depend on the selected game

## Requirements

1. Termux
2. Termux:GUI Android plugin
3. Termux:API Android plugin
4. Python
5. `termuxgui` Python package
6. `termux-api` Termux package

Install Termux and its plugins from the same source so their Android signatures match.

## Install / update

    cd ~/desk-buddy
    git pull origin main
    bash install.sh

Run:

    desk-buddy

Keep the phone reasonably still for the first couple of seconds while motion sensors calibrate.

## Diagnostics

List sensors:

    termux-sensor -l

Test motion sensors:

    termux-sensor -s Accelerometer,Gyroscope -d 100 -n 10

Test the OLED animation directly:

    desk-buddy --test-oled

Terminal fallback:

    desk-buddy --terminal

## Main files

    gui_buddy.py       native renderer, character and runtime
    buddy_advanced.py  scenes, weather, sleep and motion fusion
    game_hub.py        Tic-Tac-Toe, Pong, Snake and game menu
    gibber_voice.py    local data-chirp voice + captions
    oled_asset_show.py local OLED frame player
    desk_buddy.py      terminal fallback
    start.sh           launcher
    install.sh         installer
