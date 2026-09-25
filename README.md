# Desk Buddy

A phone-first Desk Buddy that runs directly inside Termux.

The phone screen itself becomes the Desk Buddy display. There is no website, browser UI or localhost server.

## Visual system

The current face is inspired by the visual behavior of small OLED DeskBuddy-style robots:

- Large filled rounded eyes instead of outline boxes
- Dark pupils inside bright eyes
- White reflection highlights
- Smooth gaze interpolation
- Random eye saccades
- Fast natural blinks
- Occasional double blinks
- Subtle eye breathing
- Mood-specific eye shapes
- Clean face-first layout with controls hidden after startup

Moods currently include:

- Normal
- Happy
- Love / heart eyes
- Excited
- Surprised
- Sleepy
- Focused
- Sad
- Suspicious

## Controls

While Desk Buddy is running:

- `B` = boop
- `SPACE` = random mood
- `S` = sleepy mode
- `W` = refresh weather
- `C` = cycle eye colour
- `H` = show controls again
- `Q` = quit

Eye colours currently include cyan, magenta, yellow, green, blue and white.

## Install

    pkg update
    pkg install git python gh

Clone the private repository using GitHub CLI:

    gh repo clone arjun27code/desk-buddy
    cd desk-buddy

Install the launcher:

    bash install.sh

Then run it from anywhere:

    desk-buddy

## Updating an existing clone

    cd ~/desk-buddy
    git restore start.sh
    git pull origin main
    bash install.sh
    desk-buddy

The installer no longer changes the tracked `start.sh` file mode, so normal future pulls should stay clean.

## Weather

For automatic phone location, install the Termux:API Android companion app and then:

    pkg install termux-api

Desk Buddy will use `termux-location`.

If automatic location is unavailable, save a city manually:

    desk-buddy --set-city "Your City"

Then launch normally:

    desk-buddy

Weather data comes from Open-Meteo.

## Battery

Battery reactions use:

    termux-battery-status

This requires the Termux:API companion app plus:

    pkg install termux-api

Desk Buddy still runs without Termux:API. Battery and automatic location simply remain unavailable.

## Architecture

    Android phone
        |
        |-- Termux
             |
             |-- desk_buddy.py
             |     |-- OLED-style face renderer
             |     |-- animation physics
             |     |-- moods
             |     |-- time
             |     |-- weather
             |     |-- battery reactions
             |
             |-- start.sh
             |-- install.sh

## Current limitation

This version deliberately stays inside the terminal for maximum compatibility. Termux character cells cannot match a true pixel OLED or native Android canvas exactly.

If we want genuinely smooth graphical curves, touch interaction anywhere on the face, higher frame rates and hardware-like animations, the next rendering layer should use Termux:GUI or a small native Android surface while keeping Termux as the engine.
