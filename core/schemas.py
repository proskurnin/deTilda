"""Typed Pydantic models for ``config/config.yaml`` sections."""
from __future__ import annotations

import re
from typing import Any, List

from core.pydantic_compat import BaseModel, Field


def _validate_regex(pattern: str, context: str) -> str | None:
    try:
        re.compile(pattern)
        return None
    except re.error as exc:
        return f"{context}: невалидный regex {pattern!r} — {exc}"


def validate_regex_patterns(config: "AppConfig") -> list[str]:
    """Validate all regex fields in config. Returns list of error messages."""
    errors: list[str] = []

    for i, link in enumerate(config.patterns.links):
        err = _validate_regex(link, f"patterns.links[{i}]")
        if err:
            errors.append(err)

    for i, rule in enumerate(config.patterns.replace_rules):
        err = _validate_regex(rule.pattern, f"patterns.replace_rules[{i}].pattern")
        if err:
            errors.append(err)

    for i, pattern in enumerate(config.patterns.robots_cleanup_patterns):
        err = _validate_regex(pattern, f"patterns.robots_cleanup_patterns[{i}]")
        if err:
            errors.append(err)

    for i, rule in enumerate(config.patterns.readme_cleanup_patterns):
        err = _validate_regex(rule.pattern, f"patterns.readme_cleanup_patterns[{i}].pattern")
        if err:
            errors.append(err)

    for i, pattern in enumerate(config.patterns.tilda_remnants_patterns):
        err = _validate_regex(pattern, f"patterns.tilda_remnants_patterns[{i}]")
        if err:
            errors.append(err)

    htaccess = config.patterns.htaccess_patterns
    for field_name in ("rewrite_rule", "redirect"):
        pattern = getattr(htaccess, field_name, "")
        if pattern:
            err = _validate_regex(pattern, f"patterns.htaccess_patterns.{field_name}")
            if err:
                errors.append(err)

    return errors


class ReplaceRule(BaseModel):
    pattern: str
    replacement: str = ""


class HtaccessPatterns(BaseModel):
    rewrite_rule: str = ""
    redirect: str = ""
    soft_fallback_to_404: bool = False
    auto_stub_missing_routes: bool = False
    remove_unresolved_routes: bool = True
    fallback_target: str = "404.html"


class PatternsAssets(BaseModel):
    til_to_ai_filename: str = ""


class PatternsConfig(BaseModel):
    links: List[str] = Field(default_factory=list)
    replace_rules: List[ReplaceRule] = Field(default_factory=list)
    text_extensions: List[str] = Field(default_factory=list)
    ignore_prefixes: List[str] = Field(default_factory=list)
    robots_cleanup_patterns: List[str] = Field(default_factory=list)
    readme_cleanup_patterns: List[ReplaceRule] = Field(default_factory=list)
    htaccess_patterns: HtaccessPatterns = Field(default_factory=HtaccessPatterns)
    assets: PatternsAssets = Field(default_factory=PatternsAssets)
    tilda_remnants_patterns: List[str] = Field(default_factory=list)


class DeletePhysicalFiles(BaseModel):
    as_is: List[str] = Field(default_factory=list)


class PatternsList(BaseModel):
    patterns: List[str] = Field(default_factory=list)


class LinkTagRules(BaseModel):
    rel_values: List[str] = Field(default_factory=list)


class ImagesConfig(BaseModel):
    delete_physical_files: DeletePhysicalFiles = Field(default_factory=DeletePhysicalFiles)
    comment_out_links: PatternsList = Field(default_factory=PatternsList)
    comment_out_link_tags: LinkTagRules = Field(default_factory=LinkTagRules)
    replace_links_with_1px: PatternsList = Field(default_factory=PatternsList)


class RemoteAssetRule(BaseModel):
    folder: str = ""
    extensions: List[str] = Field(default_factory=list)


class RemoteAssetsConfig(BaseModel):
    scan_extensions: List[str] = Field(default_factory=list)
    rules: List[RemoteAssetRule] = Field(default_factory=list)


class FileListConfig(BaseModel):
    files: List[str] = Field(default_factory=list)


class ScriptsToDeleteConfig(BaseModel):
    files: List[str] = Field(default_factory=list)


class ScriptsToRemoveFromProjectConfig(BaseModel):
    filenames: List[str] = Field(default_factory=list)
    patterns: List[str] = Field(default_factory=list)


class HtmlInjectOptions(BaseModel):
    inject_handler_script: str = "form-handler.js"
    inject_after_marker: str = "</body>"
    inject_head_scripts: List[str] = Field(default_factory=list)
    inject_head_marker: str = "</head>"


class NormalizeCaseConfig(BaseModel):
    enabled: bool = True
    extensions: List[str] = Field(default_factory=list)


class PipelineStagesConfig(BaseModel):
    normalize_case: NormalizeCaseConfig = Field(default_factory=NormalizeCaseConfig)


class CleanerOptionsConfig(BaseModel):
    files_to_clean_tilda_refs: List[str] = Field(default_factory=list)


class RenameMapOutputConfig(BaseModel):
    filename: str = "{project}_rename_map.json"
    location: str = "logs"


class ResourceCopyItem(BaseModel):
    source: str
    destination: str
    originals: List[str] = Field(default_factory=list)


class ResourceCopyConfig(BaseModel):
    files: List[ResourceCopyItem] = Field(default_factory=list)


class ServiceFilesConfig(BaseModel):
    remote_assets: RemoteAssetsConfig = Field(default_factory=RemoteAssetsConfig)
    exclude_from_rename: FileListConfig = Field(default_factory=FileListConfig)
    scripts_to_delete: ScriptsToDeleteConfig = Field(default_factory=ScriptsToDeleteConfig)
    scripts_to_remove_from_project: ScriptsToRemoveFromProjectConfig = Field(
        default_factory=ScriptsToRemoveFromProjectConfig
    )
    html_inject_options: HtmlInjectOptions = Field(default_factory=HtmlInjectOptions)
    pipeline_stages: PipelineStagesConfig = Field(default_factory=PipelineStagesConfig)
    cleaner_options: CleanerOptionsConfig = Field(default_factory=CleanerOptionsConfig)
    rename_map_output: RenameMapOutputConfig = Field(default_factory=RenameMapOutputConfig)
    resource_copy: ResourceCopyConfig = Field(default_factory=ResourceCopyConfig)

    @property
    def scripts_to_remove(self) -> List[str]:
        return list(self.scripts_to_remove_from_project.filenames)


class AppConfig(BaseModel):
    patterns: PatternsConfig = Field(default_factory=PatternsConfig)
    images: ImagesConfig = Field(default_factory=ImagesConfig)
    service_files: ServiceFilesConfig = Field(default_factory=ServiceFilesConfig)
