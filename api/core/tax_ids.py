"""CPF and numeric/alphanumeric CNPJ validation, without registry lookups."""

import re


def normalize_tax_id(value):
    return re.sub(r"[.\-/\s]", "", str(value)).upper()


def valid_cpf(value):
    if not re.fullmatch(r"[0-9]{11}", value) or len(set(value)) == 1:
        return False
    digits = [int(item) for item in value]
    for position in (9, 10):
        remainder = sum(digits[index] * (position + 1 - index) for index in range(position)) % 11
        if digits[position] != (0 if remainder < 2 else 11 - remainder):
            return False
    return True


def valid_cnpj(value):
    if not re.fullmatch(r"[A-Z0-9]{12}[0-9]{2}", value) or len(set(value)) == 1:
        return False
    digits = [ord(item) - 48 for item in value]
    for position, weights in (
        (12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
        (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
    ):
        remainder = sum(digits[index] * weights[index] for index in range(position)) % 11
        if digits[position] != (0 if remainder < 2 else 11 - remainder):
            return False
    return True
