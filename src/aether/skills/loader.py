from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from aether.agents.lifecycle import AgentLifecycleState
from aether.skills.package import PackageAuthor, PackageDependency, SkillPackage
from aether.skills.skill import Skill, SkillDependency, SkillLifecycleCompatibility, SkillPermission


class SkillLoadError(ValueError):
    """
    Raised when a local skill package cannot be loaded.
    """


class SkillPackageLoader(ABC):
    """
    Base contract for package loading.
    """

    @abstractmethod
    def load(self, path: str | Path) -> SkillPackage:
        raise NotImplementedError


class LocalSkillPackageLoader(SkillPackageLoader):
    """
    Loads skill packages from a local directory containing a JSON manifest.
    """

    def __init__(self, manifest_name: str = "skill-package.json") -> None:
        self.manifest_name = manifest_name

    def load(self, path: str | Path) -> SkillPackage:
        package_path = Path(path)
        manifest_path = package_path / self.manifest_name
        if not manifest_path.exists():
            raise SkillLoadError(f"Missing manifest: {manifest_path}")

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return self._load_from_data(data, source_path=package_path)

    def _load_from_data(self, data: dict, *, source_path: Path | None = None) -> SkillPackage:
        try:
            skills = tuple(
                self._load_skill(item, source_path=source_path)
                for item in self._normalize_items(data["skills"])
            )
            return SkillPackage(
                name=data["name"],
                version=data["version"],
                skills=skills,
                author=self._load_author(data.get("author")),
                vendor=data.get("vendor"),
                aether_compatibility=self._normalize_strings(
                    data.get("aether_compatibility", data.get("compatibility", ()))
                ),
                dependencies=tuple(
                    self._load_package_dependency(item)
                    for item in self._normalize_items(data.get("dependencies", ()))
                ),
                package_id=data.get("package_id"),
                metadata=data.get("metadata", {}),
                source_path=source_path,
            )
        except KeyError as exc:
            raise SkillLoadError(f"Invalid skill package manifest: missing {exc.args[0]}") from exc

    def _load_skill(self, data: dict, *, source_path: Path | None = None) -> Skill:
        try:
            lifecycle_states = tuple(
                AgentLifecycleState(state.lower())
                for state in self._normalize_items(data.get("lifecycle_compatibility", ["ready", "running"]))
            )
        except ValueError as exc:
            raise SkillLoadError(f"Invalid lifecycle compatibility in skill '{data.get('name', '<unknown>')}'") from exc

        return Skill(
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "0.1.0"),
            skill_id=data.get("skill_id"),
            metadata=data.get("metadata", {}),
            requirements=self._normalize_strings(data.get("requirements", ())),
            dependencies=tuple(
                SkillDependency.from_value(item)
                for item in self._normalize_items(data.get("dependencies", ()))
            ),
            permissions=tuple(
                SkillPermission.from_value(item)
                for item in self._normalize_items(data.get("permissions", data.get("capabilities", ())))
            ),
            lifecycle_compatibility=SkillLifecycleCompatibility(agent_states=lifecycle_states),
            package_id=data.get("package_id"),
            source_path=str(source_path) if source_path is not None else None,
        )

    def _load_author(self, value: str | dict | None) -> PackageAuthor | None:
        if value is None:
            return None

        if isinstance(value, str):
            return PackageAuthor(name=value)

        return PackageAuthor(
            name=value["name"],
            email=value.get("email"),
            url=value.get("url"),
        )

    def _load_package_dependency(self, value: str | dict) -> PackageDependency:
        return PackageDependency.from_value(value)

    @staticmethod
    def _normalize_strings(value: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        return tuple(value)

    @staticmethod
    def _normalize_items(value: object) -> tuple[object, ...]:
        if value is None:
            return ()
        if isinstance(value, (str, bytes)):
            return (value,)
        return tuple(value)


# ── SkillLoader ──────────────────────────────────────────────────────────────


class SkillLoader:
    """
    Load executable skills from a directory or archive.

    This loader is **separate** from :class:`LocalSkillPackageLoader`.  It
    consumes a ``skill.yaml`` manifest (see :mod:`aether.skills.manifest`),
    validates permissions, imports the skill module dynamically, calls
    ``register(registry, context)``, and returns a :class:`~aether.skills.loaded.LoadedSkill`.

    Archive formats supported: ``.zip``, ``.tar.gz``, ``.aether-skill``
    (treated as ZIP or tar.gz based on content).

    Parameters:
        permission_policy: The :class:`~aether.skills.policy.SkillPermissionPolicy`
            used to gate skill loading.  Defaults to ``allow_all``.
    """

    def __init__(
        self,
        permission_policy: object | None = None,
    ) -> None:
        from aether.skills.policy import SkillPermissionPolicy

        self._policy = permission_policy or SkillPermissionPolicy.allow_all()

    # ── Public API ────────────────────────────────────────────────────────────

    def from_directory(self, path: str | Path, registry: object) -> object:
        """
        Load a skill from a local directory containing a ``skill.yaml``.

        Parameters:
            path: Path to the skill directory.
            registry: A :class:`~aether.tools.registry.ToolRegistry` instance.

        Returns:
            :class:`~aether.skills.loaded.LoadedSkill`

        Raises:
            SkillManifestNotFoundError: ``skill.yaml`` missing.
            InvalidSkillManifestError: manifest is invalid.
            SkillPermissionDeniedError: a permission is blocked.
            SkillToolBindingError: ``register()`` raised or did not bind correctly.
        """
        skill_dir = Path(path).resolve()
        return self._load_from_directory(skill_dir, registry)

    def from_package(self, path: str | Path, registry: object) -> object:
        """
        Load a skill from an archive (``.zip``, ``.tar.gz``, or ``.aether-skill``).

        The archive is extracted to a temporary directory.  Path traversal entries
        are rejected.  The temp dir is cleaned up on error; on success it persists
        to allow the loaded module to remain importable during the process lifetime.

        Parameters:
            path: Path to the archive file.
            registry: A :class:`~aether.tools.registry.ToolRegistry` instance.

        Returns:
            :class:`~aether.skills.loaded.LoadedSkill`

        Raises:
            InvalidSkillPackageError: archive is invalid or corrupt.
            SkillManifestNotFoundError / InvalidSkillManifestError / SkillPermissionDeniedError
                / SkillToolBindingError: propagated from :meth:`from_directory`.
        """
        import shutil
        import tempfile

        archive_path = Path(path).resolve()
        if not archive_path.exists():
            from aether.errors import InvalidSkillPackageError
            raise InvalidSkillPackageError(f"Archive not found: {archive_path}")

        tmp_dir = Path(tempfile.mkdtemp(prefix="aether_skill_"))
        try:
            self._extract_archive(archive_path, tmp_dir)
            return self._load_from_directory(tmp_dir, registry)
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_from_directory(self, skill_dir: Path, registry: object) -> object:
        """Core loading flow: manifest → permission check → import → register."""
        from aether.skills.manifest import SkillManifest
        from aether.skills.loaded import LoadedSkill

        # 1. Parse and validate manifest (raises on any problem).
        manifest = SkillManifest.from_path(skill_dir)

        # 2. Convert manifest permissions to SkillPermission objects for the policy.
        from aether.skills.skill import SkillPermission
        parsed_permissions = [SkillPermission.from_value(p) for p in manifest.permissions]

        # 3. Permission check — BEFORE any code is imported.
        self._policy.check(parsed_permissions)

        # 4. Dynamic module import.
        register_fn = self._import_entrypoint(manifest, skill_dir)

        # 5. Build context dict and call register().
        skill = manifest.to_skill()
        context = {
            "skill_id": skill.skill_id,
            "skill_name": skill.name,
            "skill_version": skill.version,
            "source_path": str(skill_dir),
        }

        tools_before = set(registry.list_tools()) if hasattr(registry, "list_tools") else set()

        try:
            register_fn(registry, context)
        except Exception as exc:
            from aether.errors import SkillToolBindingError
            raise SkillToolBindingError(
                f"Skill '{skill.skill_id}' register() raised an error: {exc}"
            ) from exc

        # Collect newly registered tool names.
        tools_after = set(registry.list_tools()) if hasattr(registry, "list_tools") else set()
        new_tools = [t.name for t in tools_after if t not in tools_before]

        return LoadedSkill(
            skill=skill,
            registered_tools=new_tools,
            source_path=skill_dir,
        )

    def _import_entrypoint(self, manifest: object, skill_dir: Path) -> object:
        """
        Import the module declared in the manifest entrypoint and return the
        callable registration function.

        sys.path is temporarily extended with *skill_dir* during import and
        restored immediately after to minimise global contamination.
        """
        import importlib.util
        import sys

        from aether.errors import InvalidSkillManifestError, SkillToolBindingError

        module_name = manifest.entrypoint.module
        function_name = manifest.entrypoint.function

        # Build a unique internal module name to avoid collisions.
        unique_name = f"_aether_skill_{manifest.id}_{manifest.version}_{module_name}".replace(".", "_").replace("-", "_")

        # Locate the module file relative to skill_dir.
        # e.g. "tools.hello" → skill_dir / tools / hello.py
        module_rel_path = Path(*module_name.split(".")).with_suffix(".py")
        module_file = skill_dir / module_rel_path

        if not module_file.exists():
            raise InvalidSkillManifestError(
                f"Entrypoint module '{module_name}' not found at expected path: {module_file}"
            )

        # Transiently add skill_dir to sys.path so relative imports inside the
        # skill module resolve correctly, then restore sys.path immediately.
        sys.path.insert(0, str(skill_dir))
        try:
            spec = importlib.util.spec_from_file_location(unique_name, module_file)
            if spec is None or spec.loader is None:
                raise InvalidSkillManifestError(
                    f"Cannot load module spec for '{module_name}' at {module_file}."
                )
            module = importlib.util.module_from_spec(spec)
            sys.modules[unique_name] = module
            spec.loader.exec_module(module)  # type: ignore[attr-defined]
        finally:
            # Always restore sys.path, even on import error.
            if str(skill_dir) in sys.path:
                sys.path.remove(str(skill_dir))

        if not hasattr(module, function_name):
            raise SkillToolBindingError(
                f"Entrypoint function '{function_name}' not found in module '{module_name}'. "
                f"Available names: {[n for n in dir(module) if not n.startswith('_')]}."
            )

        fn = getattr(module, function_name)
        if not callable(fn):
            raise SkillToolBindingError(
                f"'{module_name}.{function_name}' is not callable (got {type(fn).__name__})."
            )

        return fn

    def _extract_archive(self, archive_path: Path, dest_dir: Path) -> None:
        """
        Extract *archive_path* into *dest_dir* with path traversal protection.

        Raises:
            InvalidSkillPackageError: on corrupt archive, unsupported format, or
                a path-traversal entry.
        """
        import tarfile
        import zipfile

        from aether.errors import InvalidSkillPackageError

        suffix = archive_path.name.lower()

        if suffix.endswith(".zip") or suffix.endswith(".aether-skill"):
            # Try ZIP first (aether-skill may be ZIP or tar.gz).
            if zipfile.is_zipfile(archive_path):
                self._extract_zip(archive_path, dest_dir)
                return
            # Fall through to tar.gz if it is not a ZIP.

        if suffix.endswith(".tar.gz") or suffix.endswith(".tgz") or suffix.endswith(".aether-skill"):
            if tarfile.is_tarfile(archive_path):
                self._extract_tar(archive_path, dest_dir)
                return

        raise InvalidSkillPackageError(
            f"Unsupported or corrupt archive: {archive_path.name}. "
            "Supported formats: .zip, .tar.gz, .aether-skill."
        )

    def _extract_zip(self, archive_path: Path, dest_dir: Path) -> None:
        import zipfile
        from aether.errors import InvalidSkillPackageError

        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.infolist():
                    self._check_traversal(member.filename, dest_dir)
                zf.extractall(dest_dir)
        except zipfile.BadZipFile as exc:
            raise InvalidSkillPackageError(
                f"Corrupt or invalid ZIP archive: {archive_path.name}"
            ) from exc

    def _extract_tar(self, archive_path: Path, dest_dir: Path) -> None:
        import tarfile
        from aether.errors import InvalidSkillPackageError

        try:
            with tarfile.open(archive_path, "r:*") as tf:
                for member in tf.getmembers():
                    self._check_traversal(member.name, dest_dir)
                tf.extractall(dest_dir, filter="data")
        except tarfile.TarError as exc:
            raise InvalidSkillPackageError(
                f"Corrupt or invalid tar archive: {archive_path.name}"
            ) from exc
        except TypeError:
            # Python < 3.12 does not support filter="data"; use safe fallback.
            try:
                with tarfile.open(archive_path, "r:*") as tf:
                    for member in tf.getmembers():
                        self._check_traversal(member.name, dest_dir)
                    tf.extractall(dest_dir)
            except tarfile.TarError as exc:
                raise InvalidSkillPackageError(
                    f"Corrupt or invalid tar archive: {archive_path.name}"
                ) from exc

    @staticmethod
    def _check_traversal(member_name: str, dest_dir: Path) -> None:
        """
        Raise InvalidSkillPackageError if *member_name* would escape *dest_dir*.
        """
        from aether.errors import InvalidSkillPackageError

        # Reject absolute paths.
        if Path(member_name).is_absolute():
            raise InvalidSkillPackageError(
                f"Archive contains an absolute path entry: {member_name!r}. "
                "This is a path traversal attempt."
            )

        # Resolve the full target path and verify it stays within dest_dir.
        resolved = (dest_dir / member_name).resolve()
        try:
            resolved.relative_to(dest_dir.resolve())
        except ValueError:
            raise InvalidSkillPackageError(
                f"Archive contains a path traversal entry: {member_name!r}. "
                "Extraction aborted."
            )
