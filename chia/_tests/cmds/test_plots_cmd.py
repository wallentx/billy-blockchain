from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from chia.cmds.plots import refresh_cmd, refresh_plots, plots_cmd
from chia.cmds.cmd_classes import ChiaCliContext


class TestPlotsCommands:
    """Test plots CLI commands including the new refresh commands."""

    def test_plots_cmd_group(self):
        """Test that the plots command group works."""
        runner = CliRunner()
        result = runner.invoke(plots_cmd, ["--help"])
        assert result.exit_code == 0
        assert "refresh" in result.output

    @patch("chia.cmds.plots.asyncio.run")
    def test_refresh_cmd(self, mock_run):
        """Test that the refresh command calls the refresh_plots function."""
        runner = CliRunner()
        result = runner.invoke(plots_cmd, ["refresh"])
        assert result.exit_code == 0
        mock_run.assert_called_once()
        args, _ = mock_run.call_args
        assert args[0].__name__ == "refresh_plots"
        assert len(args) == 1

    @patch("chia.cmds.plots.asyncio.run")
    def test_refresh_hard_cmd(self, mock_run):
        """Test that the refresh --hard command calls the refresh_plots function with hard=True."""
        runner = CliRunner()
        result = runner.invoke(plots_cmd, ["refresh", "--hard"])
        assert result.exit_code == 0
        mock_run.assert_called_once()
        args, _ = mock_run.call_args
        assert args[0].__name__ == "refresh_plots"
        assert len(args) == 1

    @pytest.mark.anyio
    async def test_refresh_plots_function(self):
        """Test the refresh_plots function."""
        # Mock the HarvesterRpcClient
        mock_client = MagicMock()
        mock_client.refresh_plots = MagicMock()
        mock_client.hard_refresh_plots = MagicMock()
        mock_client.close = MagicMock()
        mock_client.await_closed = MagicMock()

        # Mock the HarvesterRpcClient.create method
        with patch("chia.cmds.plots.HarvesterRpcClient.create", return_value=mock_client):
            # Test normal refresh
            await refresh_plots(Path("/dummy/path"), False)
            mock_client.refresh_plots.assert_called_once()
            mock_client.hard_refresh_plots.assert_not_called()
            mock_client.close.assert_called_once()
            mock_client.await_closed.assert_called_once()

            # Reset mocks
            mock_client.refresh_plots.reset_mock()
            mock_client.hard_refresh_plots.reset_mock()
            mock_client.close.reset_mock()
            mock_client.await_closed.reset_mock()

            # Test hard refresh
            await refresh_plots(Path("/dummy/path"), True)
            mock_client.refresh_plots.assert_not_called()
            mock_client.hard_refresh_plots.assert_called_once()
            mock_client.close.assert_called_once()
            mock_client.await_closed.assert_called_once()

    @pytest.mark.anyio
    async def test_refresh_plots_function_exception(self):
        """Test the refresh_plots function handles exceptions."""
        # Mock the HarvesterRpcClient to raise an exception
        mock_client = MagicMock()
        mock_client.refresh_plots.side_effect = Exception("Test exception")
        mock_client.close = MagicMock()
        mock_client.await_closed = MagicMock()

        # Mock the HarvesterRpcClient.create method
        with patch("chia.cmds.plots.HarvesterRpcClient.create", return_value=mock_client):
            # Test exception handling
            await refresh_plots(Path("/dummy/path"), False)
            mock_client.refresh_plots.assert_called_once()
            mock_client.close.assert_called_once()
            mock_client.await_closed.assert_called_once() 