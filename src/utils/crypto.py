"""
Утилиты для шифрования/дешифрования чувствительных данных (токены пользователей).

Использует симметричное шифрование Fernet (AES-128-CBC + HMAC-SHA256).

Переменные окружения:
    ENCRYPTION_KEY — Fernet-ключ, сгенерированный командой:
                     python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Префикс зашифрованных токенов в базе (для обнаружения незашифрованных старых записей)
_FERNET_PREFIX = "gAAAAA"


def _get_fernet() -> Fernet:
    """Возвращает инициализированный Fernet из переменной окружения."""
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY не задан в переменных окружения. "
            "Сгенерируйте ключ: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt_token(token: str) -> str:
    """
    Шифрует токен перед сохранением в базу данных.

    Args:
        token: Открытый токен Yandex Music.

    Returns:
        Зашифрованная строка (Fernet-токен).
    """
    return _get_fernet().encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str | None:
    """
    Дешифрует токен, полученный из базы данных.

    Поддерживает backward-compatibility: если токен в базе хранится
    в открытом виде (старые записи до введения шифрования),
    возвращает его как есть и логирует предупреждение для последующей миграции.

    Args:
        encrypted_token: Строка из колонки `token` таблицы users.

    Returns:
        Открытый токен или None при ошибке дешифрования.
    """
    if not encrypted_token:
        return None

    # Пробуем дешифровать
    try:
        return _get_fernet().decrypt(encrypted_token.encode()).decode()
    except InvalidToken:
        # Если токен не похож на Fernet — это старая plaintext-запись
        if not encrypted_token.startswith(_FERNET_PREFIX):
            logger.warning(
                "Обнаружен нешифрованный токен в БД (legacy). "
                "Токен будет перезаписан при следующей авторизации пользователя."
            )
            return encrypted_token
        # Если выглядит как Fernet, но не расшифровывается — битые данные
        logger.error("Не удалось расшифровать токен: данные повреждены или неверный ENCRYPTION_KEY.")
        return None
    except Exception as e:
        logger.error(f"Непредвиденная ошибка при дешифровании токена: {e}")
        return None
