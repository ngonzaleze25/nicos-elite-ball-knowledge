ALTER TABLE dbo.matches ADD external_id BIGINT NULL, source_status NVARCHAR(24) NULL;
ALTER TABLE dbo.matches ALTER COLUMN kickoff_at NVARCHAR(40) NULL;

EXEC(N'CREATE UNIQUE INDEX UX_matches_external_id
       ON dbo.matches (external_id) WHERE external_id IS NOT NULL;');
