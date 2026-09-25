# Desk Buddy

Phone-first Desk Buddy powered by Termux.

The default version uses a native Android pixel surface through Termux:GUI. It is not a website and does not use localhost or a browser.

## Native face

The eye geometry follows the FluxGarage RoboEyes style:

- 128x64 virtual OLED geometry
- 36x36 default eyes
- 10 px gap
- 8 px corner radius
- smooth RoboEyes-style current-to-next geometry transitions
- auto blinking
- random idle repositioning
- curiosity eye stretching
- happy, tired and angry eyelid overlays

## Emotions

A quick tap cycles through:

    happy
    curious
    annoyed
    sad
    surprised
    sleepy
    love
    excited

Non-idle emotions now stay active for about 5.5 seconds before returning to idle.

Each emotion has its own transition and visual behavior:

- Happy: smooth happy eyelids, laugh bounce and fireworks
- Curious: slides toward the upper corner with sparkle effects
- Annoyed: angry eyelids, horizontal shake and stress streaks
- Sad: slow downward tired transition with rain
- Surprised: taller narrower eyes with radial burst marks
- Sleepy: slower tired transition with floating Z marks
- Love: heart-shaped eyes with floating hearts
- Excited: larger happy eyes, vertical bounce and confetti
- Dizzy: automatic shake-triggered wobble with orbiting particles

Background effects fade in and out rather than appearing instantly.

## Hand-animated expression layer

The native renderer keeps the RoboEyes geometry, but emotion entry animations now use a second animation layer inspired by frame-by-frame 128x64 OLED animation techniques:

- 64 ms pose cadence layered over the smooth 50 FPS renderer
- anticipation before a major expression
- squash and stretch
- overshoot and settle
- short pose holds
- tiny deterministic hand-drawn wobble
- asymmetry between left and right eyes
- temporary motion/accent lines around expressions
- different entry motion for each emotion

This is intentionally an animation-language adaptation, not a copy of another animation's artwork or frames.

## Expanded emotion system

Desk Buddy now has a larger autonomous emotion set:

- happy
- curious
- annoyed
- sad
- surprised
- sleepy
- love
- excited
- shy
- confused
- scared
- proud
- bored
- dizzy

Autonomous emotions are selected randomly instead of following a fixed loop, and their hold times and transition speeds vary slightly so the behavior feels less mechanical.

Emotion details now include:

- Sad: rain intensity randomly shifts between slow, medium and fast while the emotion is active. Rain uses a darker shade of the current eye color.
- Happy: proper sky rockets launch from below, leave trails and burst into multicolor fireworks behind the eyes.
- Shy: lowered glance, compressed eyes and soft blush dots.
- Confused: asymmetric eye geometry plus question-mark accents.
- Scared: tall narrow eyes, tremble and sweat-drop accents.
- Proud: lifted gaze, controlled happy lids and orbiting star glints.
- Bored: half-lidded slow drift with a small ellipsis.
- Wave: a tiny hand occasionally appears and waves. The eyes temporarily look toward the hand, then return to idle.

The random autonomous scheduler waits between expressions, lets the current expression finish, and keeps sensor reactions such as Dizzy as higher-priority interrupts.

## Motion sensors

Desk Buddy can react to the physical phone through Termux:API.

It listens to:

- Accelerometer
- Gyroscope

At startup it takes a short baseline calibration from the phone's current resting position.

After calibration:

- tilting the phone shifts and leans the eye pair with the device
- a strong shake triggers the Dizzy reaction
- shake detection uses both acceleration change and gyroscope angular speed so normal slow tilting should not trigger Dizzy

The sensor stream uses approximately 70 ms updates.

## Requirements

1. Termux
2. Python
3. Termux:GUI Android plugin
4. Termux:API Android plugin
5. Python binding: termuxgui
6. Termux package: termux-api

Important: Termux and both plugin apps must come from the same installation source because Termux plugins need matching signatures.

## Existing clone update

    cd ~/desk-buddy
    git pull origin main
    bash install.sh

Then launch:

    desk-buddy

Keep the phone reasonably still for roughly the first second so the tilt baseline can calibrate.

## Controls

Native pixel mode:

- touch and drag: eyes follow your finger
- quick tap: next emotion
- tilt phone: face leans with the device
- shake phone: Dizzy reaction
- Android Back: close the Desk Buddy activity

Terminal fallback:

    desk-buddy --terminal

## Sensor troubleshooting

Check whether Termux can see phone sensors:

    termux-sensor -l

Test accelerometer and gyroscope directly:

    termux-sensor -s Accel,Gyro -d 200 -n 5

Stop any leftover sensor listener:

    termux-sensor -c

If `termux-sensor` exists but returns nothing, confirm that the Termux:API Android plugin is installed from the same source as Termux and grant any permission Android asks for.

## Files

    gui_buddy.py     native pixel renderer, effects and sensor reactions
    desk_buddy.py    old terminal fallback
    start.sh         launcher
    install.sh       installer
