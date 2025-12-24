from mangapy.providers import available_providers, get_repository


def test_provider_registry_contains_fanfox():
    assert "fanfox" in available_providers()


def test_provider_capabilities_exposed():
    repo = get_repository("fanfox")
    caps = repo.capabilities
    assert caps.max_parallel_chapters == 1
    assert caps.max_parallel_pages == 1
