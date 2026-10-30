class RepositoryAccessError(Exception):
    pass


class InvalidRepositorySourceError(RepositoryAccessError):
    pass


class RepositoryNotFoundError(RepositoryAccessError):
    pass


class RepositorySecurityError(RepositoryAccessError):
    pass


class RepositoryLimitExceededError(RepositoryAccessError):
    pass


class WorkspaceError(RepositoryAccessError):
    pass
