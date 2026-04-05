-- SQL Server style escaping
CREATE TABLE [USR_ACCOUNT] (
    [USR_ID] INT PRIMARY KEY,
    "USR_NAME" VARCHAR(100),
    [DESC] TEXT -- Potential reserved word collision
);

-- Mixed identifiers
ALTER TABLE [USR_ACCOUNT] ADD COLUMN USR_ID_OLD INT;

-- Verify that renaming 'USR_ID' does not touch 'USR_ID_OLD'
INSERT INTO [USR_ACCOUNT] ([USR_ID], "USR_NAME") VALUES (1, 'Architect');