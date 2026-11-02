"""Command line: python -m card_generator product.json [more.json ...] [--out DIR] [--json]"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from .card import ProductCard
from .generator import generate_card
from .llm import LLMClient, LLMError
from .product import InputError, parse_product_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m card_generator",
        description="Черновик карточки товара для B2B-магазина по данным о приборе.",
    )
    parser.add_argument("files", nargs="+", type=Path, help="JSON-файлы с данными о товарах")
    parser.add_argument("--out", type=Path, help="папка для карточек (.md и .json); без неё карточка печатается в консоль")
    parser.add_argument("--json", action="store_true", help="печатать JSON вместо Markdown")
    args = parser.parse_args(argv)

    # Our own progress messages only: httpx would add a line for every request.
    logging.basicConfig(format="  %(message)s")
    logging.getLogger("card_generator").setLevel(logging.INFO)

    load_dotenv()
    try:
        llm = LLMClient.from_env()
    except LLMError as error:
        print(f"Ошибка настройки: {error}", file=sys.stderr)
        return 2

    failed = False
    for path in args.files:
        try:
            product = parse_product_json(_read(path))
            print(f"{path}: готовлю карточку…", file=sys.stderr)
            card = generate_card(product, llm)
        except (InputError, LLMError) as error:
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
            continue

        if args.out:
            _save(card, args.out, path.stem)
        elif args.json:
            print(card.model_dump_json(indent=2))
        else:
            print(card.to_markdown())
    return 1 if failed else 0


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise InputError("файл не найден") from None
    except OSError as error:
        raise InputError(f"не удалось прочитать файл ({error.strerror})") from None


def _save(card: ProductCard, folder: Path, name: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(card.to_markdown(), encoding="utf-8")
    (folder / f"{name}.json").write_text(card.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"  сохранено: {folder / name}.md и .json", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
