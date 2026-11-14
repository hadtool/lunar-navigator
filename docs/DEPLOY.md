# Деплой приложения (T14)

Заметка для команды. Приложение читает только `data/processed/` (3,6 МБ, в git) и `docs/`; рельеф
LOLA и ядра SPICE ему не нужны. Зависимости для облака — `app/requirements.txt` (streamlit, plotly,
numpy, pandas, pyarrow, spiceypy, версии как в `uv.lock`).

Проверено 2026-11-14: в чистом окружении Python 3.12 только с этими шестью пакетами (rasterio не
установлен) все шесть страниц открываются без ошибок (`AppTest`).

## Что решает команда до публикации

1. **Сделать репозиторий публичным.** Секретов в отслеживаемых файлах нет (проверено поиском по
   ключам, токенам, паролям и закрытым ключам; совпадения — только примеры в документации агента
   ревью). Но **во всех коммитах указан личный адрес автора (Gmail)** — в публичном репозитории он
   будет виден в истории. Варианты: оставить как есть; или до публикации переписать автора коммитов
   на адрес вида `<логин>@users.noreply.github.com` (это переписывает историю и требует
   принудительного push — только по решению команды).
2. **Запушить локальные коммиты** в `origin/main` (сейчас локальная ветка впереди).

## Streamlit Community Cloud (основной вариант)

1. https://share.streamlit.io → войти через GitHub (делает команда).
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
