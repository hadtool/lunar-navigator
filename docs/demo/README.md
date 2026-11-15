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

## Still to do by the team

- Done 2026-11-15: the video `demo_video.mp4` is public in the repository; a YouTube upload is optional.
- Replace the placeholders `[names]` and `[link]` on slide 1 (edit `pipeline/make_slides.py` and
  rebuild, or edit the PDF).
