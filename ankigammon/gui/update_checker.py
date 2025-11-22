"""Version update checker using GitHub Releases API."""

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict
from urllib.parse import urlparse

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

# GitHub repository info
REPO_OWNER = "Deinonychus999"
REPO_NAME = "AnkiGammon"
GITHUB_API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases"


class VersionChecker:
    """Check for updates via GitHub Releases API."""

    def __init__(self, timeout: int = 5):
        """Initialize version checker.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout

    def check_latest_version(self, current_version: Optional[str] = None) -> Optional[Dict]:
        """Fetch latest release from GitHub API with changelog since current version.

        Args:
            current_version: Current app version to generate changelog from (optional)

        Returns:
            Dict with release info or None if failed:
            {
                'version': '1.0.7',
                'name': 'Version 1.0.7',
                'release_notes': '...',  # Combined notes from all missed versions
                'download_url': 'https://...',
                'published_at': '2024-01-15T10:30:00Z'
            }
        """
        try:
            import requests
        except ImportError:
            logger.warning("requests library not available, cannot check for updates")
            return None

        try:
            # Fetch all releases to get changelog
            all_releases_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"
            response = requests.get(
                all_releases_url,
                timeout=(self.timeout, self.timeout),
                headers={'Accept': 'application/vnd.github+json'}
            )
            response.raise_for_status()

            releases = response.json()

            # Filter out pre-releases and drafts, get stable releases only
            stable_releases = [
                r for r in releases
                if not r.get('prerelease') and not r.get('draft')
            ]

            if not stable_releases:
                logger.info("No stable releases found")
                return None

            # Latest release is first in the list
            latest = stable_releases[0]
            latest_version = latest.get('tag_name', '').lstrip('v')

            # If we have current version, get all releases since then
            combined_notes = latest.get('body', '')
            if current_version:
                try:
                    from packaging.version import Version
                    missed_releases = []

                    for release in stable_releases:
                        release_version = release.get('tag_name', '').lstrip('v')
                        try:
                            if Version(release_version) > Version(current_version):
                                missed_releases.append(release)
                        except Exception:
                            continue

                    # Combine release notes (newest first)
                    if len(missed_releases) > 1:
                        notes_parts = []
                        for release in missed_releases:
                            version = release.get('tag_name', '').lstrip('v')
                            body = release.get('body', '').strip()
                            if body:
                                # Add version header to each block
                                notes_parts.append(f"## Version {version}\n\n{body}")

                        combined_notes = "\n\n---\n\n".join(notes_parts)
                        logger.info(f"Combined {len(missed_releases)} release notes")
                except Exception as e:
                    logger.warning(f"Failed to combine release notes: {e}")
                    # Fall back to just latest release notes
                    combined_notes = latest.get('body', '')

            return {
                'version': latest_version,
                'name': latest.get('name', latest_version),
                'release_notes': combined_notes,
                'download_url': self._extract_download_url(latest),
                'published_at': latest.get('published_at', ''),
                'html_url': latest.get('html_url', GITHUB_RELEASES_URL)
            }
        except Exception as e:
            logger.warning(f"Failed to check for updates: {e}")
            return None

    def _extract_download_url(self, release_data: Dict) -> str:
        """Extract appropriate download URL from release data.

        Uses GitHub's /releases/latest/download/ URL pattern for direct downloads.
        """
        # Determine platform-specific filename
        if sys.platform == 'win32':
            # Windows: ankigammon-windows.zip
            filename = 'ankigammon-windows.zip'
        elif sys.platform == 'darwin':
            # macOS: AnkiGammon-macOS.dmg
            filename = 'AnkiGammon-macOS.dmg'
        else:
            # Linux: AnkiGammon-x86_64.AppImage
            filename = 'AnkiGammon-x86_64.AppImage'

        # Construct direct download URL using GitHub's /releases/latest/download/ pattern
        download_url = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/latest/download/{filename}"

        return download_url

    def compare_versions(self, current: str, latest: str) -> bool:
        """Check if latest version is newer than current.

        Args:
            current: Current version string (e.g., "1.0.6")
            latest: Latest version string

        Returns:
            True if update is available
        """
        try:
            from packaging.version import Version
            return Version(latest) > Version(current)
        except Exception as e:
            logger.warning(f"Failed to compare versions: {e}")
            return False


class VersionCheckCache:
    """Manages version check caching to avoid excessive API calls."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize cache manager.

        Args:
            cache_dir: Directory for cache file (defaults to ~/.ankigammon)
        """
        if cache_dir is None:
            cache_dir = Path.home() / '.ankigammon'
        self.cache_file = cache_dir / 'version_check.json'
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def should_check(self, min_hours_between_checks: int = 24) -> bool:
        """Check if enough time has passed since last check.

        Args:
            min_hours_between_checks: Minimum hours between checks

        Returns:
            True if should check now
        """
        if not self.cache_file.exists():
            return True

        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)

            last_check = datetime.fromisoformat(cache.get('last_check', ''))
            time_since_check = datetime.now() - last_check

            return time_since_check > timedelta(hours=min_hours_between_checks)
        except (json.JSONDecodeError, ValueError, KeyError, OSError):
            return True  # If cache is corrupted, check anyway

    def get_cached_update(self) -> Optional[Dict]:
        """Get previously cached update info.

        Returns:
            Cached release info or None
        """
        if not self.cache_file.exists():
            return None

        try:
            with open(self.cache_file, 'r') as f:
                cache = json.load(f)
            return cache.get('latest_release')
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def save_check(self, release_info: Optional[Dict]):
        """Save the result of a version check.

        Args:
            release_info: Release info dict or None
        """
        cache = {
            'last_check': datetime.now().isoformat(),
            'latest_release': release_info
        }

        try:
            with open(self.cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save version check cache: {e}")


class VersionCheckerThread(QThread):
    """Background thread for non-blocking version checking."""

    # Signals
    update_available = Signal(dict)  # Emitted when update found
    check_complete = Signal()  # Emitted when check done
    check_failed = Signal()  # Emitted when check failed (network error)

    def __init__(self, current_version: str, force_check: bool = False):
        """Initialize checker thread.

        Args:
            current_version: Current app version
            force_check: If True, bypass cache and check immediately
        """
        super().__init__()
        self.current_version = current_version
        self.force_check = force_check
        self.checker = VersionChecker()
        self.cache = VersionCheckCache()

    def run(self):
        """Execute version check in background thread."""
        try:
            # Check if we should skip (unless forced)
            if not self.force_check and not self.cache.should_check(min_hours_between_checks=6):
                logger.info("Skipping version check (too recent)")
                cached = self.cache.get_cached_update()
                if cached:
                    self._check_and_emit(cached)
                self.check_complete.emit()
                return

            # Fetch from GitHub
            logger.info("Checking for updates...")
            latest = self.checker.check_latest_version(current_version=self.current_version)

            if latest:
                # Cache the result
                self.cache.save_check(latest)
                self._check_and_emit(latest)
            else:
                # Network failure - try cached value
                logger.info("Network check failed, using cache")
                cached = self.cache.get_cached_update()
                if cached:
                    self._check_and_emit(cached)
                elif self.force_check:
                    # Manual check with no network and no cache = fail
                    self._check_failed = True
                    self.check_failed.emit()

            self.check_complete.emit()
        except Exception as e:
            logger.error(f"Version check thread error: {e}")
            self.check_complete.emit()

    def _check_and_emit(self, release_info: Dict):
        """Check if update is available and emit signal.

        Args:
            release_info: Release information dict
        """
        if self.checker.compare_versions(self.current_version, release_info['version']):
            logger.info(f"Update available: {release_info['version']}")
            self.update_available.emit(release_info)
        else:
            logger.info(f"Already up to date ({self.current_version})")
