"""Studio HTTP handlers — thin per contracts/http-routes.md.

Every handler: authenticate (middleware) → optionally check the DraftLease
hash → call the existing CLI/library code path → render the result. A handler
that grows business logic is a review-time defect (FR-001).
"""
