from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Character Pipeline Backend"
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"])
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"
    dashscope_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DASHSCOPE_API_KEY", "APP_DASHSCOPE_API_KEY"),
    )
    dashscope_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/api/v1",
        validation_alias=AliasChoices("DASHSCOPE_BASE_URL", "APP_DASHSCOPE_BASE_URL"),
    )
    # 千面动捕（qmai.vip）开放平台凭证，所有动作捕捉接口均使用该 key 作为 companyKey
    qmai_company_key: str = Field(
        default="",
        validation_alias=AliasChoices("QMAI_COMPANY_KEY", "APP_QMAI_COMPANY_KEY"),
    )
    qmai_base_url: str = Field(
        default="https://www.qmai.vip/business",
        validation_alias=AliasChoices("QMAI_BASE_URL", "APP_QMAI_BASE_URL"),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        extra="ignore",
    )

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def asset_index_dir(self) -> Path:
        return self.assets_dir / "_index"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for path in (
        settings.jobs_dir,
        settings.assets_dir,
        settings.asset_index_dir,
        settings.logs_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return settings
