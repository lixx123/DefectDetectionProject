"""Storage failures are distinct from detection failures."""
class RepositoryError(Exception): pass
class ResultAlreadyExistsError(RepositoryError): pass
class ResultNotFoundError(RepositoryError): pass
class PackageIntegrityError(RepositoryError): pass
class ManifestError(PackageIntegrityError): pass
class UnsafeArtifactPathError(PackageIntegrityError): pass
class RepositoryIndexError(RepositoryError): pass
class ConfigSnapshotError(PackageIntegrityError): pass
