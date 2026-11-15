# Demo materials (tasks T17, T25, T27)

| File | What it is |
|---|---|
| `deck/index.html` with `deck/data.js`, `deck/img/`, `deck/fonts/` | **The demo: seven animated slides** (a web page, 1920 x 1080 stage that scales to the window) |
| `slides.pdf`, `slides/slide_1.png` ... `slide_7.png` | Static copy of the same seven slides (every slide in its final state) |
| `demo_video.mp4`, `video_script.md`, `subtitles.srt` | 30-second video with English subtitles and a visible "AI-generated video" mark; an extra, not the submitted demo |
| `screenshots/` | Screens of the app along the demo scenario (local run, 2026-11-15) |

## The deck

Open `deck/index.html` in a browser (it works from the file system) or the public link.
Keys: arrows or space to move, `1`-`7` or the dots of the flight path to jump, `Home`/`End`,
`R` replays the landing, `A` plays the deck by itself, `F` is full screen; a click or a swipe moves on.
`?static=1` shows a slide without animation.

Slides: 1 title (liftoff) · 2 the problem · 3 the tool · 4 NASA data · 5 the mast · 6 limits and
next steps · 7 touchdown. Between slides a rocket flies across, the stars streak and the Moon moves
on; the flight path at the bottom shows where the deck is.

What is data and what is illustration:

| On the slides | Source |
|---|---|
| The Moon | Shaded relief of the LOLA 40 m model, 440 km across around the south pole; the dots are the 15 sites of the tool at their real positions |
| Sun, Earth and terrain on slides 2 and 5 | A replay of the project's own results: horizon of Malapert Massif at 2 m and 10 m, hourly Sun and Earth positions and the visible share of the solar disc, 8 April to 21 May 2027 |
| Batteries on slide 5 | The hourly simulation of the app for the year 2027 (default lander), the same window; the failure date and the lowest charge are those of the Power page |
| All numbers | `deck/data.js`, written by `pipeline/make_deck.py` from the result files; figures of the validation are checked against docs/VALIDATION.md when the file is built |
| App screens | The screenshots in `screenshots/` |
| Rocket, astronauts, flags, landing scene, Earth and Sun discs of the last slide | Illustration, generated with AI and marked as such; not a mission plan |

Rebuild after the results or the app changed:

    uv run --with segno python pipeline/make_deck.py    # data.js, Moon picture, app screens, font, QR code
    uv run python pipeline/export_deck.py               # slides.pdf and slides/*.png (needs Firefox)

Rules of the guide and how the deck meets them: seven slides, not more; English; team members,
challenge, an image of the project, the user's three clicks and the NASA data are on slides 1, 3
and 4; every slide carries the line "AI-generated deck"; no NASA logos, flags or mission
identifiers (the astronauts wear their national flags and the deck's own patch); no people.

## Requirements (checked against the 2026 guide, T26)

Source: Project Submission Guide, https://www.spaceappschallenge.org/resources/project-submission-guide/
(page dated November 13, 2026; saved by the team on 2026-11-15, see docs/SOURCES.md):

- the demo is either a slide deck of **up to seven slides, including the title and intro slides**,
  or a video of **30 seconds or less**; "Projects that exceed these limits will not be eligible for
  Global Judging";
- slides must show an image of the project, describe the user experience, include how NASA and
  space-agency open data and technology make the solution possible, and name the team, its members
  and the challenge;
- the demo is **linked**, not uploaded: a public link without password, permission or registration
  (GitHub is named as an acceptable host);
- everything is **in English**;
- content made with AI ("SI" in the guide) may not use NASA logos, flags or mission identifiers;
  AI-generated images and videos **must carry a visible watermark**; code and data must acknowledge
  it in text and metadata;
- no images, video, audio or other likeness of persons under 18.

