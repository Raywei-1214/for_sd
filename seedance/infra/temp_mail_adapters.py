from dataclasses import dataclass


@dataclass(frozen=True)
class TempMailAdapter:
    name: str
    ready_selectors: tuple[str, ...]
    email_value_selectors: tuple[str, ...]
    email_text_selectors: tuple[str, ...]
    email_attribute_selectors: tuple[tuple[str, str], ...]
    verification_text_markers: tuple[str, ...]


GENERIC_TEMP_MAIL_ADAPTER = TempMailAdapter(
    name="generic",
    ready_selectors=(
        "input",
        "body",
    ),
    email_value_selectors=(
        "input[value*='@']",
        "input[readonly]",
    ),
    email_text_selectors=(
        "#email",
        "span#email",
        "div#email",
        "p#email",
        ".email",
        ".address",
        "span.address",
        "div.email-address",
        ".email-address",
        "#eposta_adres",
        "#address",
        "#address-value",
        "#mail_address",
        "[data-testid*='email']",
        "[data-testid*='address']",
        "[aria-label*='email' i]",
        "[aria-label*='address' i]",
        "[class*='email']",
        "[class*='address']",
    ),
    email_attribute_selectors=(
        ("[data-clipboard-text]", "data-clipboard-text"),
        ("[data-email]", "data-email"),
        ("[data-address]", "data-address"),
        ("[aria-label*='email' i]", "aria-label"),
        ("[aria-label*='address' i]", "aria-label"),
    ),
    verification_text_markers=(
        "verification code",
        "验证码",
        "code is",
    ),
)


TEMP_MAIL_ADAPTERS: dict[str, TempMailAdapter] = {
    "mail.tm": TempMailAdapter(
        name="mail.tm",
        ready_selectors=(
            "input[readonly]",
            "#address",
            ".email",
        ),
        email_value_selectors=(
            "input[readonly][value*='@']",
            "input[value*='@mail.tm']",
        ),
        email_text_selectors=(
            "#address",
            ".email",
            ".address",
        ),
        email_attribute_selectors=(
            ("[data-clipboard-text]", "data-clipboard-text"),
        ),
        verification_text_markers=(
            "verification code",
            "dreamina",
            "capcut",
        ),
    ),
    "10minutemail.net": TempMailAdapter(
        name="10minutemail.net",
        ready_selectors=(
            "#mail_address",
            "#address",
            "input[value*='@']",
        ),
        email_value_selectors=(
            "#mail_address",
            "input[value*='@']",
        ),
        email_text_selectors=(
            "#mail_address",
            "#address",
            "#address-value",
        ),
        email_attribute_selectors=(
            ("[data-clipboard-text]", "data-clipboard-text"),
        ),
        verification_text_markers=(
            "verification code",
            "code is",
            "dreamina",
        ),
    ),
    "internxt": TempMailAdapter(
        name="internxt",
        ready_selectors=(
            "input[readonly]",
            "button[aria-label*='copy' i]",
            "[data-testid*='email']",
            "[data-testid*='address']",
            ".email-address",
            ".address",
        ),
        email_value_selectors=(
            "input[readonly][value*='@']",
            "input[value*='@']",
        ),
        email_text_selectors=(
            ".email-address",
            ".address",
            "#email",
            "[data-testid*='email']",
            "[data-testid*='address']",
            "[aria-label*='email' i]",
            "[aria-label*='address' i]",
            "button[aria-label*='copy' i]",
        ),
        email_attribute_selectors=(
            ("[data-email]", "data-email"),
            ("[data-address]", "data-address"),
            ("[data-clipboard-text]", "data-clipboard-text"),
            ("button[aria-label*='copy' i]", "data-clipboard-text"),
            ("button[aria-label*='email' i]", "aria-label"),
        ),
        verification_text_markers=(
            "verification code",
            "code is",
            "dreamina",
        ),
    ),
    "mailpoof": TempMailAdapter(
        name="mailpoof",
        ready_selectors=(
            "#email",
            "input[name='email']",
            "input[placeholder*='email' i]",
            "#selected-domain",
            ".email-address",
            "input[value*='@']",
        ),
        email_value_selectors=(
            "input[value*='@']",
            "input[name='email'][value]",
        ),
        email_text_selectors=(
            "#email",
            "#selected-domain",
            ".email-address",
            ".email",
            "input[name='email']",
        ),
        email_attribute_selectors=(
            ("[data-clipboard-text]", "data-clipboard-text"),
            ("input[name='email']", "value"),
        ),
        verification_text_markers=(
            "verification code",
            "code is",
            "dreamina",
        ),
    ),
    "tempmail.lol": TempMailAdapter(
        name="tempmail.lol",
        ready_selectors=(
            "#email",
            "#mail_address",
            "input[value*='@']",
        ),
        email_value_selectors=(
            "input[value*='@']",
        ),
        email_text_selectors=(
            "#email",
            "#mail_address",
            ".email",
        ),
        email_attribute_selectors=(
            ("[data-clipboard-text]", "data-clipboard-text"),
        ),
        verification_text_markers=(
            "verification code",
            "code is",
        ),
    ),
    "crazymailing": TempMailAdapter(
        name="crazymailing",
        ready_selectors=(
            ".email",
            ".address",
            "input[value*='@']",
        ),
        email_value_selectors=(
            "input[value*='@']",
        ),
        email_text_selectors=(
            ".email",
            ".address",
            ".email-address",
        ),
        email_attribute_selectors=(),
        verification_text_markers=(
            "verification code",
            "验证码",
        ),
    ),
}


def get_temp_mail_adapter(provider_name: str) -> TempMailAdapter:
    return TEMP_MAIL_ADAPTERS.get(provider_name, GENERIC_TEMP_MAIL_ADAPTER)
