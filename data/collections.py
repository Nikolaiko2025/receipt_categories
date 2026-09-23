receipt_categories_db = [
    {
        "id": 1,
        "title": "Оплата по дебиторке",
        "type": "income",
        "category": "debit",
        "category_display": "Дебиторка",
        "amount": 1200000.00,
        "date": "2026-09-15",
        "description": "Поступление от ООО 'Ромашка' по договору №45",
        "image_url": "http://localhost:9000/image/Оплата по дебиторке.jpg",
        "video_url": "http://localhost:9000/image/оплата_по_дебиторке.mp4",
        "likes": [0, 2, 5, 7, 9],
        "status": "Опубликован"
    },
    {
        "id": 2,
        "title": "Продажа товаров",
        "type": "income",
        "category": "sales",
        "category_display": "Продажи",
        "amount": 850000.00,
        "date": "2026-09-20",
        "description": "Реализация товаров через маркетплейс",
        "image_url": "http://localhost:9000/image/Продажа товаров.jpg",
        "video_url": "http://localhost:9000/image/продажа_товаров.mp4",
        "likes": [1, 3, 6],
        "status": "Опубликован"
    },
    {
        "id": 3,
        "title": "Погашение кредита",
        "type": "expense",
        "category": "credit",
        "category_display": "Кредит",
        "amount": -300000.00,
        "date": "2026-09-10",
        "description": "Ежемесячный платеж по кредитному договору",
        "image_url": "http://localhost:9000/image/Погашение кредита.png",
        "video_url": "http://localhost:9000/image/погашение_кредита.mp4",
        "likes": [2, 8],
        "status": "Опубликован"
    },
    {
        "id": 4,
        "title": "Выплата зарплаты",
        "type": "expense",
        "category": "salary",
        "category_display": "Зарплата",
        "amount": -450000.00,
        "date": "2026-09-25",
        "description": "Заработная плата сотрудников за август",
        "image_url": "http://localhost:9000/image/Выплата зарплаты.jpg",
        "video_url": "http://localhost:9000/image/выплата_зарплаты.mp4",
        "likes": [0, 4, 7, 10],
        "status": "Опубликован"
    },
    {
        "id": 5,
        "title": "Расчет с поставщиками",
        "type": "expense",
        "category": "suppliers",
        "category_display": "Поставщики",
        "amount": -280000.00,
        "date": "2026-09-18",
        "description": "Оплата за поставленные материалы",
        "image_url": "http://localhost:9000/image/Расчет с поставщиками.jpg",
        "video_url": "http://localhost:9000/image/расчет_с_поставщиками.mp4",
        "likes": [3, 5],
        "status": "Опубликован"
    },
    {
        "id": 6,
        "title": "Новый проект — внедрение CRM",
        "type": "income",
        "category": "sales",
        "category_display": "Продажи",
        "amount": 2000000.00,
        "date": "2026-10-01",
        "description": "Поступление от внедрения CRM-системы",
        "image_url": "http://localhost:9000/image/Новый проект — внедрение CRM.jpg",
        "video_url": "http://localhost:9000/image/hotel_vid copy 5.mp4",
        "likes": [],
        "status": "Черновик"
    },
    {
        "id": 7,
        "title": "Удаленная операция",
        "type": "income",
        "category": "debit",
        "category_display": "Дебиторка",
        "amount": 500000.00,
        "date": "2026-09-05",
        "description": "Тестовая удаленная операция",
        "image_url": "http://localhost:9000/image/Оплата по дебиторке1.jpg",
        "video_url": "http://localhost:9000/image/оплата_по_дебиторке.mp4",
        "likes": [],
        "status": "Удален"
    }
]


def get_published():
    return [rc for rc in receipt_categories_db if rc["status"] == "Опубликован"]


def get_by_id(receipt_category_id: int):
    for rc in receipt_categories_db:
        if rc["id"] == receipt_category_id:
            return rc
    return None


def get_next_after(receipt_category_id: int):
    published = get_published()
    for i, rc in enumerate(published):
        if rc["id"] == receipt_category_id:
            if i + 1 < len(published):
                return published[i + 1]
            return None
    return None
