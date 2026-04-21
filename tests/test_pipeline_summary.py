from core.pipeline import DetildaPipeline, PipelineStats


def test_status_message_considers_html_prettify_skip() -> None:
    stats = PipelineStats(html_prettify_skipped=True, warnings=0, errors=0)
    assert DetildaPipeline._status_message(stats) == "завершено с предупреждениями"
