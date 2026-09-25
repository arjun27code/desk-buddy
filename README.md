# Desk Buddy

Phone-first smart Desk Buddy built to run locally on Android through Termux.

## MVP features

- Cute animated face with blinking eyes
- Eyes follow pointer and touch movement
- Tap and button reactions
- Curious, excited, sleepy, surprised, love and focused moods
- Local time and date
- Local weather through browser location and Open-Meteo
- Optional phone battery status through Termux:API
- Browser speech for simple voice reactions
- Full-screen face mode
- No Python framework or third-party Python packages
- One-command launch after installation: desk-buddy

## How it works

Termux runs one small Python HTTP server on the phone. The server hosts the HTML, CSS and JavaScript interface on localhost and provides tiny endpoints for weather and optional battery data.

There is no Docker, database or cloud backend in the MVP. A blinking pair of eyes does not need enterprise infrastructure, despite the software industry's best efforts.

## Install on Termux

Install Git and Python:

    pkg update
    pkg install git python

Clone the repository:

    git clone https://github.com/arjun27code/desk-buddy.git
    cd desk-buddy

While the MVP is on its review branch, switch to it:

    git switch desk-buddy-mvp

Run the installer once:

    bash install.sh

After that, start Desk Buddy from any Termux directory with:

    desk-buddy

Desk Buddy starts its local server and opens:

    http://127.0.0.1:8765

Press Ctrl+C in Termux to stop it.

## Optional battery support

The rest of Desk Buddy works without Termux:API.

To show phone battery information:

1. Install the Termux:API companion Android app from the same source as your Termux installation.
2. In Termux run:

       pkg install termux-api

3. Restart Desk Buddy.

The battery command used by the MVP is termux-battery-status.

## Weather

Allow location access when your browser asks for it.

The browser provides latitude and longitude to the local Desk Buddy server. The server uses them for the current Open-Meteo request. Desk Buddy does not save the coordinates.

## Useful commands

Start without automatically opening the browser:

    desk-buddy --no-open

Use another local port:

    DESK_BUDDY_PORT=9000 desk-buddy

Then open:

    http://127.0.0.1:9000

## Current architecture

    Termux
      |
      |-- start.sh
      |-- server.py
      |     |-- /api/health
      |     |-- /api/weather
      |     |-- /api/battery
      |
      |-- web/
            |-- index.html
            |-- styles.css
            |-- app.js
      |
      |-- Android browser

## Next upgrades

The current branch is intentionally an MVP foundation. Useful next upgrades include:

1. Charging and low-battery animations
2. Android notification reactions
3. Reminder and timer actions
4. Sound packs
5. Voice commands
6. Configurable personality
7. Optional LLM integration
8. Wake-lock or kiosk-style always-on mode
