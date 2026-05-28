import os
import json
import tempfile
import sys
import pytest
from unittest.mock import patch, MagicMock


def create_mock_module(name):
    """Helper to create a mock module"""
    mock_module = MagicMock()
    sys.modules[name] = mock_module
    return mock_module


@pytest.fixture(autouse=True)
def mock_all_dependencies():
    # Mock all required dependencies
    # Mock third-party packages
    create_mock_module('loguru')
    create_mock_module('fastapi')
    create_mock_module('fastapi.APIRouter')
    create_mock_module('pytz')
    create_mock_module('sqlalchemy')
    create_mock_module('sqlalchemy.orm')
    create_mock_module('collector')
    create_mock_module('collector.db')
    create_mock_module('collector.db.database')
    create_mock_module('collector.db.models')
    
    # Mock utils package and all submodules
    utils = create_mock_module('utils')
    utils.logger = create_mock_module('utils.logger')
    utils.decorators = create_mock_module('utils.decorators')
    utils.i18n = create_mock_module('utils.i18n')
    utils.jwt_utils = create_mock_module('utils.jwt_utils')
    utils.number_utils = create_mock_module('utils.number_utils')
    utils.time_parser = create_mock_module('utils.time_parser')
    utils.timezone = create_mock_module('utils.timezone')
    
    # Add the required functions to utils.logger
    utils.logger.get_logger = MagicMock(return_value=MagicMock())
    utils.logger.get_plugin_logger = MagicMock(return_value=MagicMock())
    utils.logger.LogType = MagicMock()
    
    # Add the required decorators
    utils.decorators.async_deco_retry = lambda *args, **kwargs: lambda f: f
    utils.decorators.deco_retry = lambda *args, **kwargs: lambda f: f
    
    yield


class TestPluginBase:
    def test_initialization(self):
        from plugins.plugin_base import PluginBase
        plugin = PluginBase("test_plugin", "1.0.0")
        assert plugin.name == "test_plugin"
        assert plugin.version == "1.0.0"
        assert plugin.load_type == "hot"
        assert not plugin.is_active
        assert plugin.plugin_manager is None

    def test_register(self):
        from plugins.plugin_base import PluginBase
        plugin = PluginBase("test_plugin", "1.0.0")
        mock_manager = MagicMock()
        plugin.register(mock_manager)
        assert plugin.plugin_manager == mock_manager

    def test_start_stop(self):
        from plugins.plugin_base import PluginBase
        plugin = PluginBase("test_plugin", "1.0.0")
        plugin.start()
        assert plugin.is_active
        plugin.stop()
        assert not plugin.is_active

    def test_get_info(self):
        from plugins.plugin_base import PluginBase
        plugin = PluginBase("test_plugin", "1.0.0")
        info = plugin.get_info()
        assert info["name"] == "test_plugin"
        assert info["version"] == "1.0.0"
        assert info["load_type"] == "hot"
        assert not info["is_active"]

    def test_get_metadata(self):
        from plugins.plugin_base import PluginBase
        plugin = PluginBase("test_plugin", "1.0.0")
        metadata = plugin.get_metadata()
        assert metadata["name"] == "test_plugin"
        assert metadata["version"] == "1.0.0"
        assert metadata["load_type"] == "hot"


class TestEventBus:
    @pytest.fixture
    def event_bus(self):
        from plugins.event_bus import EventBus
        return EventBus()

    def test_subscribe_and_publish(self, event_bus):
        called = []

        def callback(data):
            called.append(data)

        event_bus.subscribe("test_event", callback)
        event_bus.publish("test_event", {"key": "value"})

        assert len(called) == 1
        assert called[0] == {"key": "value"}

    def test_unsubscribe(self, event_bus):
        called = []

        def callback(data):
            called.append(data)

        event_bus.subscribe("test_event", callback)
        event_bus.unsubscribe("test_event", callback)
        event_bus.publish("test_event", {"key": "value"})

        assert len(called) == 0

    def test_multiple_subscribers(self, event_bus):
        called1 = []
        called2 = []

        def callback1(data):
            called1.append(data)

        def callback2(data):
            called2.append(data)

        event_bus.subscribe("test_event", callback1)
        event_bus.subscribe("test_event", callback2)
        event_bus.publish("test_event", {"key": "value"})

        assert len(called1) == 1
        assert len(called2) == 1

    def test_clear(self, event_bus):
        called = []

        def callback(data):
            called.append(data)

        event_bus.subscribe("test_event", callback)
        event_bus.clear()
        event_bus.publish("test_event", {"key": "value"})

        assert len(called) == 0


