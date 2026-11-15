# Деплой приложения (T14)

Заметка для команды. Приложение читает только `data/processed/` (3,6 МБ, в git) и `docs/`; рельеф
LOLA и ядра SPICE ему не нужны. Зависимости для облака — `app/requirements.txt` (streamlit, plotly,
numpy, pandas, pyarrow, spiceypy, версии как в `uv.lock`).

Проверено 2026-11-14: в чистом окружении Python 3.12 только с этими шестью пакетами (rasterio не
установлен) все шесть страниц открываются без ошибок (`AppTest`).

## Публикация (сделано 2026-11-15)

1. По решению команды адрес автора во всех коммитах заменён на маску Firefox Relay
   (история переписана до первой публикации, `git filter-branch --env-filter`); новые коммиты
   идут с тем же адресом (`git config user.email`).
2. Ветка `main` отправлена в `origin`, репозиторий сделан публичным.

## Streamlit Community Cloud (основной вариант)

1. https://share.streamlit.io → **Continue with GitHub** (аккаунт Streamlit отдельно создавать не нужно: вход
   через GitHub-аккаунт `hadtool` и есть регистрация; делает команда).
2. Create app → Deploy a public app from GitHub:
   - Repository: `hadtool/lunar-navigator`, Branch: `main`;
   - Main file path: `app/streamlit_app.py`;
   - Advanced settings → Python version: **3.12** (код требует 3.12+);
   - App URL: на выбор, например `lunar-landing-navigator`.
3. Deploy. Первая сборка ставит зависимости из `app/requirements.txt` (файл рядом с точкой входа
   имеет приоритет).
4. Проверка (условие «Готово» T14): открыть ссылку в приватном окне браузера без входа, пройти
   все шесть страниц и демо-сценарий: Malapert Massif → Power («Does not survive» на 2 м) → мачта
   10 м («Survives»).

## Hugging Face Spaces (запасной вариант)

Space с SDK Streamlit: в репозиторий Space нужны `requirements.txt` в корне (можно скопировать
`app/requirements.txt`) и заголовок README Space с `sdk: streamlit` и `app_file: app/streamlit_app.py`.
Не делался: основной вариант проще.

## После деплоя

- Записать ссылку в README (T16) и в материалы подачи (T17).
- При изменении данных: `uv run python pipeline/build.py` локально, коммит `data/processed/`, push —
  Community Cloud перезапустит приложение сам.
