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


## Advanced companion runtime

The current native version also includes:

- Android TTS through `termux-tts-speak`
- synchronized native captions at the bottom of the screen
- a live clock in the top-right corner
- full-screen scene engine
- full-screen sad rain
- full-screen happy rocket fireworks
- bike ride scene
- car drive scene
- walking scene
- park/bench scene
- rainbow scene
- ambient rain scene
- autonomous sleep
- shake-to-wake
- accelerometer + gyroscope complementary fusion
- sensor-name discovery using `termux-sensor -l`

### Scene behavior

Scenes appear autonomously while Desk Buddy is idle. They do not interrupt an active emotion.

Bike mode uses a moving road, lane motion and handlebar/wheel cues.

Car mode uses a moving perspective road, dashboard and steering wheel.

Walk mode scrolls trees and ground details.

Park mode shows a tree, bench and bird motion.

Rainbow mode renders a multi-colour arc behind the face.

Rain mode uses full-screen drops rather than restricting rain to the 128x64 face area.

### Speech and captions

Whenever Desk Buddy says something, the same phrase is shown as a caption near the bottom of the native activity.

Speech uses:

    termux-tts-speak

Captions still work even if Android TTS is unavailable.

### Sleep and wake

Desk Buddy can enter a real sleep state with closed eyes and a night background.

A strong physical shake wakes it up and triggers a short surprised wake reaction.

Touching the sleeping face also wakes it.

### Sensor fusion

The motion system now discovers the actual sensor names reported by the phone and requests those names from Termux:API.

Tilt uses a complementary filter:

- gyroscope handles fast angular motion
- accelerometer gravity corrects gyroscope drift

Shake detection uses both acceleration jerk and gyroscope angular speed.

Useful checks:

    termux-sensor -l

and:

    termux-sensor -s Accelerometer,Gyroscope -d 100 -n 10

If the phone uses vendor-specific sensor names, Desk Buddy should discover them automatically.


## Vision, camera attention and five-finger trigger

The advanced native runtime can use the front camera through Termux:API.

Camera behavior:

- discovers the actual front-camera id using `termux-camera-info`
- captures low-rate local snapshots with `termux-camera-photo`
- mirrors the image so left/right eye contact feels natural
- detects the largest visible face locally with OpenCV
- moves the eyes toward the person's horizontal and vertical position
- watches a mostly stationary visible person and eventually gets bored
- boredom can trigger an annoyed reaction, walk, park or screen-edge peek
- detects a stable open palm / five-finger gesture and starts the special doodle animation
- camera snapshots are kept only in Termux cache and deleted immediately after each analysis

The camera path is deliberately local. It does not upload photos.

Termux:API exposes still camera capture rather than a continuous native video stream, so face tracking runs at a modest snapshot cadence and the RoboEyes interpolation smooths movement between observations.

### Five-finger animation

The attached 128x64 OLED material was analyzed for its animation language: discrete frame cadence, large expressive eyes, pose-to-pose acting, tiny hand-drawn jitter, body poses and secondary hand/heart motion.

The five-finger trigger starts an original 102-frame doodle sequence at the same 64 ms frame cadence. It does not reproduce lyric text or copy the original bitmap artwork.

## Gibber-style voice

Human TTS is no longer the default audible voice.

Desk Buddy now creates short local FSK-style robotic data chirps and plays them with:

    termux-media-player

The actual human-readable phrase appears in the bottom caption chip.

This is intentionally a GibberLink-style sound aesthetic, not a claim of ggwave/GibberLink wire compatibility.

## Modern scene system

The procedural scenes now use the full application canvas.

Bike:
- perspective road
- parallax city/trees
- speed streaks
- animated handlebars, stem, wheels and spokes

Car:
- moving city perspective
- windshield framing
- dashboard
- animated steering wheel
- instrument lights

Weather:
- storm clouds arrive before rain
- rain covers the full screen
- slow / medium / fast rain modes
- lightning flash and bolt
- sunny mode with glowing sun and moving clouds
- night mode with stars, moon and shooting star
- full rainbow with clouds, shimmer and glints

Sleep:
- night gradient
- stars and moon
- actual little bed
- pillow and blanket
- mini sleeping Buddy
- floating animated Z marks
- shake or touch wakes Buddy

Peek:
- Buddy leans partly beyond the screen edge
- small gripping fingers appear at the edge
- curiosity marks animate outside the apparent display boundary

## Camera prerequisites

Camera intelligence additionally needs OpenCV. The installer attempts:

    pkg install x11-repo
    pkg install opencv-python python-numpy

Checks:

    termux-camera-info

    python -c "import cv2, numpy; print(cv2.__version__)"

The first camera capture may ask Android for Camera permission. Grant it to the Termux:API companion app.

## Update after this release

    cd ~/desk-buddy
    git pull origin main
    bash install.sh
    desk-buddy

Keep the phone reasonably still for the first couple of seconds for motion-sensor calibration.


## Right-hand five-finger OLED trigger

The mirrored front-camera vision layer now distinguishes a five-finger open-palm gesture on the user's right-hand side.

When the right hand is detected stably for multiple camera snapshots:

1. Desk Buddy wakes if needed.
2. It starts the local Arduino OLED frame sequence.
3. The animation frame order comes from `epd_bitmap_allArray`.
4. The frame delay is read from the local Arduino sketch when available.
5. After the sequence finishes, Desk Buddy returns to its normal personality.

The large bitmap payload is not duplicated inside the repository. The player reads the user's local copy directly.

Supported filenames:

    animation_frames.h
    animation_frames(1).h

Optional sketch timing files:

    loveMeNotOledLyrics.ino
    loveMeNotOledLyrics(1).ino

These can be kept in the project folder or the phone Downloads folder.

If Termux cannot read Downloads, run once:

    termux-setup-storage

Then grant the Android storage permission.

## Front-camera preview

The mirrored front camera is also rendered as a small preview in the top-right corner of the native pixel canvas.

- source: front camera
- opacity: 40%
- no separate Android overlay window
- camera frame is alpha-blended directly into the Desk Buddy render buffer
- the clock has moved to top-center so it does not overlap the preview
- `CAM● RH5` appears when a stable right-hand five-finger pose is currently detected


## Performance and right-hand reliability update

The native renderer is now tuned for phone hardware rather than trying to brute-force a desktop-style refresh loop:

- render cadence reduced from 50 FPS to 30 FPS
- render buffer reduced from up to 400x920 to about 320x720
- camera analysis width reduced from 480px to 360px
- camera uses a normal low-rate scan and automatically enters a faster burst when a possible right-hand palm appears
- camera preview stays at 40% alpha
- OLED bitmap rows are precomputed once at load time instead of rescanning all 8192 source pixels every displayed frame

The open-palm detector was also changed:

- smaller morphology kernel preserves gaps between fingers
- broader YCrCb + HSV skin masks improve lighting tolerance
- smaller distant hands are accepted
- three strong finger valleys can promote an open-palm result
- a stricter two-valley fallback handles merged fingers in low-light snapshots
- only a candidate on the user's mirrored right-hand side can fire the right-hand OLED trigger
- the HUD shows `CAM RH4?` while a likely palm is being confirmed and `CAM● RH5` when it is confirmed

### Isolate OLED playback from camera detection

Run:

    desk-buddy --test-oled

This starts the local OLED frame file immediately. If the animation plays in this mode but not from the hand gesture, the frame loader is healthy and only vision calibration needs attention.

The terminal also prints the detected right-hand confidence and the OLED file/frame count when a gesture fires.


### Isolate camera gesture detection

Run:

    desk-buddy --vision-test

For about 18 seconds it prints one line per fresh camera snapshot with:

- face detected
- estimated finger count
- right-hand candidate flag
- confirmed RH5 flag
- open-palm confidence
- horizontal hand position

It exits early with PASS when the exact right-hand open-palm event fires.
