# Задание 2. Классификация заказов через LLM API

Алексеенко Данил Витальевич, группа Б9123-01.0.02ии.

## Описание задачи

Скрипт читает транзакции из CSV-файла с продажами розничной сети,
отправляет каждую транзакцию в LLM через OpenRouter API и получает
структурированную классификацию в формате JSON.

Категории классификации:

| Категория | Описание |
|---|---|
| `normal` | Обычная розничная транзакция с положительной прибылью |
| `bulk_order` | Легитимный оптовый заказ (большое количество единиц) |
| `data_error` | Подозрительная запись, возможная ошибка ввода (например, продажа на $10000 при quantity=1) |
| `loss_making` | Убыточная транзакция из-за высокой скидки |
| `return` | Возврат товара (отрицательное количество) |

## Стек

- Python 3.10+
- requests, python-dotenv
- LLM: Qwen 2.5 72B Instruct через OpenRouter API
- temperature=0 для воспроизводимости

## Структура

```
task2_pipeline/
├── classify_orders.py     # основной скрипт
├── data/
│   ├── superstore_sales.csv     # входные данные (2000 строк)
│   └── classified_orders.json   # результат работы
├── requirements.txt
├── .env.example
└── README.md
```

## Установка и запуск

1. Клонировать репозиторий и перейти в папку проекта:
   ```bash
   git clone <repo-url>
   cd task2_pipeline
   ```

2. Создать виртуальное окружение и установить зависимости:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # на Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Скопировать `.env.example` в `.env` и вписать ключ OpenRouter:
   ```bash
   cp .env.example .env
   # отредактировать .env и подставить реальный ключ
   ```

   Ключ можно получить бесплатно на https://openrouter.ai/keys

4. Запустить скрипт:
   ```bash
   python3 classify_orders.py --limit 50
   ```

   Параметры:
   - `--input` (по умолчанию `data/superstore_sales.csv`) — путь к CSV
   - `--output` (по умолчанию `data/classified_orders.json`) — путь к JSON-результату
   - `--limit` (по умолчанию 50) — сколько строк обработать
   - `--model` (по умолчанию `qwen/qwen-2.5-72b-instruct`) — slug модели в OpenRouter

## Формат входных данных

CSV-файл со столбцами:

```
Order ID, Order Date, Ship Date, Ship Mode, Customer ID, Segment, Region,
State, Category, Sub-Category, Quantity, Unit Price, Discount, Sales, Profit
```

Пример входной строки:

```csv
US-2024-000564,2023-08-14,2023-08-17,Standard Class,CG-12345,Corporate,West,California,Technology,Copiers,56,966.32,0.0,54113.86,9740.49
```

## Формат выходных данных

JSON-массив объектов:

```json
[
  {
    "order_id": "US-2024-000564",
    "order_date": "2023-08-14",
    "category": "Technology",
    "sub_category": "Copiers",
    "quantity": 56,
    "sales": 54113.86,
    "profit": 9740.49,
    "discount": 0.0,
    "llm_classification": {
      "category": "bulk_order",
      "confidence": 0.95,
      "reason": "Quantity of 56 units strongly indicates a wholesale order."
    }
  }
]
```

## Как это работает

1. Скрипт читает CSV в память построчно.
2. Каждая строка превращается в текстовый промпт со всеми полями.
3. Запрос отправляется в OpenRouter с системным промптом, требующим
   строго JSON-ответ заданной формы.
4. Ответ модели парсится через регулярку плюс `json.loads()`, при
   неудаче выполняется до 3 попыток.
5. Все результаты собираются в один массив и сохраняются в JSON.
6. В консоли выводится распределение по категориям для контроля.

## Обработка ошибок

- Отсутствие ключа в `.env` — скрипт завершится с понятной ошибкой.
- Сетевые сбои или невалидный JSON от модели — до 3 повторных попыток
  с задержкой 5 секунд.
- Если после повторов запрос всё равно не прошёл, в результат пишется
  объект с `category: "error"` и текстом ошибки, обработка остальных
  строк продолжается.
