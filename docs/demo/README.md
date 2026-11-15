# Demo materials (task T17)

| File | What it is |
|---|---|
| `slides.pdf`, `slides/slide_1.png` ... `slide_7.png` | Seven slides, 16:9, English (title included) |
| `video_script.md` | 30-second video: screen, action and subtitle per second |
| `subtitles.srt` | English subtitles for the video |
| `demo_video.mp4` | The 30-second video (1920 x 1080, H.264, subtitles burned in), built from the app screenshots of 2026-11-15 with ffmpeg; no people, no voice |
| `screenshots/` | Key screens of the app along the demo scenario (local run, 1600 x 914) |

Rebuild: start the app (`uv run streamlit run app/streamlit_app.py`), take new screenshots if the
app changed, then `uv run python pipeline/make_slides.py`. The slide numbers are read from the
mast trade-off table (`data/processed/mast/`); the other numbers come from docs/VALIDATION.md.

## Requirements as found (to be confirmed by the team)

Source: the official Project Submission Guide page,
https://www.spaceappschallenge.org/resources/project-submission-guide/, as quoted by a web search on
2026-11-14. The page itself could not be opened from our tools (certificate and proxy errors), and it
may still show the previous year's wording, so **check the 2026 guide before submitting**:

- the project demo is either a video of **30 seconds or less** or a slide deck of **at most seven
  slides, including the title and intro slides**;
- the slides must show how NASA and space-agency open data and technology make the solution
  possible (slide 6);
- videos and slides are not uploaded to the Space Apps site but **linked** from the project page,
  so they need a public link (for example: the PDF in the public repository or in Google Drive, the
  video on YouTube);
- the submission page and all linked materials must be **in English**;
- no images, video, audio or other likeness of persons under 18.

## Still to do by the team

- Done 2026-11-15: the video `demo_video.mp4` is public in the repository; a YouTube upload is optional.
- Replace the placeholders `[names]` and `[link]` on slide 1 (edit `pipeline/make_slides.py` and
  rebuild, or edit the PDF).
