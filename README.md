# Flibook

Flibook – локальная электронная библиотека на базе дампа электронной библиотеки с INPX-файлом.
Основной режим использования - веб-интерфейс на Flask (а значит, будет работать с любым браузером и без JavaScript).

## Что понадобится

* Python ≥ 3.9 с `pip`.
* GNU/Linux, macOS или Windows (тестировалось на Linux).
* Дамп
  * `*.inpx` файл – метаданные.
  * каталоги/архивы с самими fb2/обложками (необязательно для индексации, но понадобится для обложек / скачивания).

Установите зависимости:

```bash
pip install -r requirements.txt
```

*(В `requirements.txt` заданы минимальные версии, можно брать новее.)*

## Быстрый старт

### 1. Создать и заполнить базу книг

```bash
python -m flibook.cli build path/to/library_index.inpx \
                        --dump-root path/to/fb2_dump
```

По умолчанию`flibook.db` будет создан в текущей директории.

Параметры:

* `--db-url` – путь к SQLite/другой СУБД (SQLAlchemy URI).
* `--chunk-size` – размер партии вставок (по умолчанию 1000).

### 2. Запустить сервер

Важно: команды `python -m flibook.cli …` выполняйте из **родительского каталога**, где находится папка `flibook/`.  
Если вы зайдёте внутрь самой директории, импорт сломается (Python ищет пакет `flibook` на уровне `sys.path`).

Минимальный запуск (когда база уже есть):

```bash
# из корня (там, где лежит папка flibook/)
python -m flibook.cli           # то же, что `run`
```

CLI автоматически вызывает `run` (cервер).  
Он стартует на `http://127.0.0.1:5000`.

Если вы уже находитесь внутри `flibook/`, используйте прямой вызов модуля:

```bash
python cli.py build /path/to/dump.inpx
python cli.py run
```

Или оставайтесь в корне проекта и явно указывайте команду:

```bash
python -m flibook.cli run               # default host=127.0.0.1 port=5000
python -m flibook.cli run --debug       # hot-reload
python -m flibook.cli run --host 0.0.0.0 --port 8080
```

## Возможности поиска

Вводите слова из названия книги или имени автора в любом порядке (регистр неважен).  
Ищутся совпадения в:

* `title`
* `author.last_name`
* `author.first_name`
* `author.middle_name`

Пример: `иванов алексей` найдёт «Пищеблок», «Речфлот» и др.

## Структура проекта (кратко)

```
flibook/
├── assembler.py        # сборка fb2 при скачивании
├── importer.py         # индексатор INPX → SQLite
├── cli.py              # CLI (build / run)
├── web.py              # Flask-приложение
├── models.py           # SQLAlchemy ORM модели
├── static/             # CSS, JS, изображения
└── templates/          # Jinja2-шаблоны
```

## Полезные советы

* **Ресканирование дампа**: выполните `build` поверх существующей БД – записи будут переиспользованы.
* **Альтернативная СУБД**: например, задайте `--db-url postgresql://user:pass@localhost/flibook` (не тестировалось!)

---

Made with ❤︎ for personal offline reading.
