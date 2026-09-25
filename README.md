# Desk Buddy

A phone-first Desk Buddy that runs directly inside Termux.

This is not a website and does not use localhost or a browser. The phone screen itself becomes the Desk Buddy display.

## Current behavior

- Full-screen terminal face
- Cyan animated eyes
- Random blinking
- Eyes look around automatically
- Happy, sleepy, surprised and focused expressions
- Cute idle messages
- Time and date
- Optional battery reactions
- Optional weather reactions
- Charging and low-battery reactions
- Night-time sleepy behavior
- One command launch: `desk-buddy`

## Controls

While Desk Buddy is running:

- `B` = boop
- `SPACE` = random reaction
- `S` = sleep reaction
- `W` = refresh weather
- `Q` = quit

## Install

    pkg update
    pkg install git python gh

Clone the private repository using GitHub CLI:

    gh repo clone arjun27code/desk-buddy
    cd desk-buddy

Install the launcher:

    bash install.sh

After that you can run it from anywhere:

    desk-buddy

## Updating an existing clone

If you already cloned the repository:

    cd ~/desk-buddy
    git pull origin main
    bash install.sh

Then run:

    desk-buddy

## Weather

For automatic phone location, install the Termux:API Android companion app and then:

    pkg install termux-api

Desk Buddy will use `termux-location`.

If you do not want Termux:API location, save a city manually:

    desk-buddy --set-city "Your City"

Then launch normally:

    desk-buddy

Weather data comes from Open-Meteo.

## Battery

Battery reactions use:

    termux-battery-status

This requires the Termux:API companion app plus:

    pkg install termux-api

Without Termux:API the Desk Buddy still runs. Battery and automatic location are simply unavailable.

## Architecture

    Android phone
        |
        |-- Termux
             |
             |-- desk_buddy.py
             |     |-- animated terminal face
             |     |-- time
             |     |-- weather
             |     |-- battery reactions
             |
             |-- start.sh
             |-- install.sh

There is no HTTP server, browser UI, HTML, CSS or JavaScript in the active implementation.

## Next phase

The direct-Termux version is the compatibility-first base. A later visual upgrade can use Termux:GUI for a native Android activity with smoother graphical eyes while keeping Termux as the engine.
