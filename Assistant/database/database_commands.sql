-- ============================================================================
-- Developer Assistant - Database Schema
-- ============================================================================
-- This script creates all tables for the Developer Assistant application
-- Optimized for Databricks Delta Lake with performance enhancements
-- ============================================================================

-- ----------------------------------------------------------------------------
-- CONFIGURATION
-- ----------------------------------------------------------------------------
USE CATALOG ai_solutions_development;
USE SCHEMA dev_assist_pilot;

-- For production, update catalog/schema as needed
-- ============================================================================


-- ============================================================================
-- DROP EXISTING TABLES (Development Only - Uncomment to recreate)
-- ============================================================================
-- DROP TABLE IF EXISTS ai_solutions_development.dev_assist_pilot.conversations;
-- DROP TABLE IF EXISTS ai_solutions_development.dev_assist_pilot.chat_messages;
-- DROP TABLE IF EXISTS ai_solutions_development.dev_assist_pilot.chat_activity_log;


-- ============================================================================
-- TABLE DEFINITIONS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. CONVERSATIONS TABLE
-- ----------------------------------------------------------------------------
-- Stores conversation metadata (chat history list)
-- 
-- ACCESS PATTERNS:
-- - List conversations by user (most recent first)
-- - Get conversation by chat_id + user_id
-- - Update message_count and updated_at frequently
-- - Soft deletes (set deleted = true)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_solutions_development.dev_assist_pilot.conversations (
  chat_id STRING NOT NULL,
  user_id STRING NOT NULL,
  title STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  message_count INT,
  deleted BOOLEAN,
  deleted_at TIMESTAMP,
  
  PRIMARY KEY (chat_id, user_id)
) USING DELTA
CLUSTER BY (user_id, chat_id)
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.enableDeletionVectors' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.columnMapping.mode' = 'name',
  'delta.autoOptimize.autoCompact' = 'true'
);

COMMENT ON TABLE ai_solutions_development.dev_assist_pilot.conversations IS 
'Conversation metadata with frequent updates. Optimized for user-based queries and soft deletes.';


-- ----------------------------------------------------------------------------
-- 2. CHAT MESSAGES TABLE
-- ----------------------------------------------------------------------------
-- Stores individual messages within conversations
-- 
-- ACCESS PATTERNS:
-- - Get all messages for a conversation (user_id + chat_id)
-- - Order by created_at (chronological display)
-- - Update token counts after LLM responses
-- - Soft deletes (set deleted = true)
--
-- TOKEN TRACKING:
-- - input_tokens: CUMULATIVE context sent to LLM (system + history)
--                 Only populated for assistant messages
-- - output_tokens: Response tokens from LLM (assistant messages only)
-- - cache_*_tokens: Prompt caching metrics (reduces costs ~50%)
--
-- CONTEXT CALCULATION:
-- - Current context = last_assistant_input_tokens + sum(all_output_tokens)
-- - Billable tokens = (input_tokens - cached_tokens) + output_tokens
--
-- OPTIMIZATIONS:
-- - CLUSTER BY (user_id, chat_id, created_at): Perfect for conversation retrieval
-- - Deletion vectors: Fast updates for token counts
-- - Auto-compact: Handles high update volume
-- - Short retention (7 days): Messages don't need long history
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_solutions_development.dev_assist_pilot.chat_messages (
  message_id STRING NOT NULL,
  chat_id STRING NOT NULL,
  user_id STRING NOT NULL,
  role STRING NOT NULL,
  content STRING NOT NULL,
  created_at TIMESTAMP NOT NULL,
  llm_model STRING,
  input_tokens INT,
  output_tokens INT,
  cache_creation_input_tokens INT,
  cache_read_input_tokens INT,
  deleted BOOLEAN,
  deleted_at TIMESTAMP,
  
  PRIMARY KEY (message_id, user_id, chat_id)
) USING DELTA
CLUSTER BY (user_id, chat_id, created_at)
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.enableDeletionVectors' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.columnMapping.mode' = 'name',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.deletedFileRetentionDuration' = 'interval 7 days'
);

COMMENT ON TABLE ai_solutions_development.dev_assist_pilot.chat_messages IS 
'Individual messages with token tracking. High update volume - optimized with deletion vectors and auto-compact.';


-- ----------------------------------------------------------------------------
-- 3. CHAT ACTIVITY LOG TABLE
-- ----------------------------------------------------------------------------
-- Stores audit trail and analytics data (append-only)
-- 
-- ACCESS PATTERNS:
-- - Analytics queries by date range
-- - User activity reports
-- - Token usage tracking
-- - Compliance/audit queries
--
-- VOLUME: < 1K rows/day (too small for daily partitioning)
--
-- OPTIMIZATIONS:
-- - CLUSTER BY (log_date, user_id): Efficient date + user filtering
-- - NO partitioning: Volume too low, would create tiny files
-- - NO deletion vectors: Append-only table (no updates/deletes)
-- - Longer retention (90 days): Audit/compliance requirements
--
-- DATA RETENTION:
-- - Use DELETE + OPTIMIZE + VACUUM for old data cleanup
-- - Consider archiving to cold storage after 1 year
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_solutions_development.dev_assist_pilot.chat_activity_log (
  log_id STRING NOT NULL,
  log_date DATE NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  user_name STRING,
  user_email STRING,
  user_id STRING NOT NULL,
  chat_id STRING NOT NULL,
  message_id STRING NOT NULL,
  message_type STRING NOT NULL,
  selected_llm STRING,
  input_tokens INT,
  output_tokens INT,
  cache_creation_input_tokens INT,
  cache_read_input_tokens INT,
  session_id STRING,
  ip_address STRING,
  user_agent STRING,
  
  PRIMARY KEY (log_id, log_date)
) USING DELTA
CLUSTER BY (log_date, user_id)
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.columnMapping.mode' = 'name',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.logRetentionDuration' = 'interval 90 days',
  'delta.deletedFileRetentionDuration' = 'interval 30 days'
);

COMMENT ON TABLE ai_solutions_development.dev_assist_pilot.chat_activity_log IS 
'Append-only audit log. Clustered by date for analytics. No partitioning due to low volume (<1K rows/day).';


-- ----------------------------------------------------------------------------
-- GUARDRAILS ASSESSMENTS TABLE
-- ----------------------------------------------------------------------------
-- Stores guardrails evaluation results and audit trail (append-only)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_solutions_development.dev_assist_pilot.guardrail_assessments (
  assessment_id STRING NOT NULL,
  user_id STRING NOT NULL,
  session_id STRING NOT NULL,
  chat_id STRING,
  prompt_text STRING,
  assessment_result STRING NOT NULL,  -- APPROVED/REJECTED/FLAGGED_FOR_REVIEW
  risk_level STRING NOT NULL,  -- NONE/LOW/MEDIUM/HIGH/CRITICAL
  violation_types STRING,  -- JSON array as string
  reasoning STRING,
  confidence_score DOUBLE,
  processing_time_ms BIGINT,
  model_used STRING,
  input_tokens INT,
  output_tokens INT,
  guardrails_bypassed BOOLEAN NOT NULL,  -- Must explicitly set FALSE/TRUE
  system_error BOOLEAN NOT NULL,  -- Must explicitly set FALSE/TRUE
  created_at TIMESTAMP NOT NULL,
  reviewed_by STRING,
  review_notes STRING,
  review_timestamp TIMESTAMP,

  PRIMARY KEY (assessment_id, user_id)
) USING DELTA
CLUSTER BY (user_id, created_at)
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.columnMapping.mode' = 'name',
  'delta.autoOptimize.autoCompact' = 'true',
  'delta.logRetentionDuration' = 'interval 90 days',
  'delta.deletedFileRetentionDuration' = 'interval 30 days'
);

COMMENT ON TABLE ai_solutions_development.dev_assist_pilot.guardrail_assessments IS 
'Guardrails evaluation audit log. Append-only with encrypted sensitive fields. Clustered for user isolation and time-based queries.';

-- ============================================================================
-- INITIAL OPTIMIZATION (Optional - Run after first data load)
-- ============================================================================
-- These are optional since CLUSTER BY handles most optimization automatically
-- Only run if you notice performance issues after initial data load

-- OPTIMIZE ai_solutions_development.dev_assist_pilot.conversations;
-- OPTIMIZE ai_solutions_development.dev_assist_pilot.chat_messages;
-- OPTIMIZE ai_solutions_development.dev_assist_pilot.chat_activity_log;


-- ============================================================================
-- MAINTENANCE SCHEDULE
-- ============================================================================
-- Recommended maintenance tasks for production

-- ----------------------------------------------------------------------------
-- DAILY MAINTENANCE (During low-traffic hours)
-- ----------------------------------------------------------------------------
-- For conversations and chat_messages (high update volume)
/*
OPTIMIZE ai_solutions_development.dev_assist_pilot.conversations
WHERE updated_at >= current_date() - INTERVAL 7 DAYS;

OPTIMIZE ai_solutions_development.dev_assist_pilot.chat_messages
WHERE created_at >= current_date() - INTERVAL 7 DAYS;
*/

-- ----------------------------------------------------------------------------
-- WEEKLY MAINTENANCE
-- ----------------------------------------------------------------------------
-- Clean up old file versions (frees storage)
/*
VACUUM ai_solutions_development.dev_assist_pilot.conversations RETAIN 168 HOURS;
VACUUM ai_solutions_development.dev_assist_pilot.chat_messages RETAIN 168 HOURS;
*/

-- Optimize activity log (append-only, less frequent)
/*
OPTIMIZE ai_solutions_development.dev_assist_pilot.chat_activity_log
WHERE log_date >= current_date() - INTERVAL 60 DAYS;
*/

-- ----------------------------------------------------------------------------
-- MONTHLY MAINTENANCE
-- ----------------------------------------------------------------------------
-- Full table optimization and cleanup
/*
OPTIMIZE ai_solutions_development.dev_assist_pilot.conversations;
OPTIMIZE ai_solutions_development.dev_assist_pilot.chat_messages;
OPTIMIZE ai_solutions_development.dev_assist_pilot.chat_activity_log;

VACUUM ai_solutions_development.dev_assist_pilot.chat_activity_log RETAIN 720 HOURS;
*/

-- Delete old activity logs (compliance/retention policy)
/*
DELETE FROM ai_solutions_development.dev_assist_pilot.chat_activity_log
WHERE log_date < current_date() - INTERVAL 365 DAYS;

OPTIMIZE ai_solutions_development.dev_assist_pilot.chat_activity_log;
VACUUM ai_solutions_development.dev_assist_pilot.chat_activity_log RETAIN 720 HOURS;
*/


-- ============================================================================
-- MONITORING QUERIES
-- ============================================================================
-- Use these to monitor table health and performance

-- ----------------------------------------------------------------------------
-- Table Statistics
-- ----------------------------------------------------------------------------
-- Check table sizes and file counts
SELECT 
  'conversations' as table_name,
  numFiles,
  sizeInBytes / 1024 / 1024 / 1024 as size_gb,
  numDeletionVectors,
  ROUND(numDeletionVectors * 100.0 / NULLIF(numFiles, 0), 2) as deletion_vector_ratio_pct
FROM (DESCRIBE DETAIL ai_solutions_development.dev_assist_pilot.conversations)

UNION ALL

SELECT 
  'chat_messages' as table_name,
  numFiles,
  sizeInBytes / 1024 / 1024 / 1024 as size_gb,
  numDeletionVectors,
  ROUND(numDeletionVectors * 100.0 / NULLIF(numFiles, 0), 2) as deletion_vector_ratio_pct
FROM (DESCRIBE DETAIL ai_solutions_development.dev_assist_pilot.chat_messages)

UNION ALL

SELECT 
  'chat_activity_log' as table_name,
  numFiles,
  sizeInBytes / 1024 / 1024 / 1024 as size_gb,
  0 as numDeletionVectors,
  0 as deletion_vector_ratio_pct
FROM (DESCRIBE DETAIL ai_solutions_development.dev_assist_pilot.chat_activity_log);

-- If deletion_vector_ratio_pct > 50%, run OPTIMIZE

-- ----------------------------------------------------------------------------
-- File Size Distribution
-- ----------------------------------------------------------------------------
-- Check for small file problems
SELECT 
  'conversations' as table_name,
  COUNT(*) as num_files,
  ROUND(AVG(size) / 1024 / 1024, 2) as avg_file_size_mb,
  ROUND(MIN(size) / 1024 / 1024, 2) as min_file_size_mb,
  ROUND(MAX(size) / 1024 / 1024, 2) as max_file_size_mb
FROM ai_solutions_development.dev_assist_pilot.conversations.files

UNION ALL

SELECT 
  'chat_messages' as table_name,
  COUNT(*) as num_files,
  ROUND(AVG(size) / 1024 / 1024, 2) as avg_file_size_mb,
  ROUND(MIN(size) / 1024 / 1024, 2) as min_file_size_mb,
  ROUND(MAX(size) / 1024 / 1024, 2) as max_file_size_mb
FROM ai_solutions_development.dev_assist_pilot.chat_messages.files

UNION ALL

SELECT 
  'chat_activity_log' as table_name,
  COUNT(*) as num_files,
  ROUND(AVG(size) / 1024 / 1024, 2) as avg_file_size_mb,
  ROUND(MIN(size) / 1024 / 1024, 2) as min_file_size_mb,
  ROUND(MAX(size) / 1024 / 1024, 2) as max_file_size_mb
FROM ai_solutions_development.dev_assist_pilot.chat_activity_log.files;

-- If avg_file_size_mb < 50 and many files, run OPTIMIZE


-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Run these after table creation to verify everything is correct

-- Check table structures
DESCRIBE EXTENDED ai_solutions_development.dev_assist_pilot.conversations;
DESCRIBE EXTENDED ai_solutions_development.dev_assist_pilot.chat_messages;
DESCRIBE EXTENDED ai_solutions_development.dev_assist_pilot.chat_activity_log;

-- Verify table properties
SHOW TBLPROPERTIES ai_solutions_development.dev_assist_pilot.conversations;
SHOW TBLPROPERTIES ai_solutions_development.dev_assist_pilot.chat_messages;
SHOW TBLPROPERTIES ai_solutions_development.dev_assist_pilot.chat_activity_log;

-- Check record counts
SELECT 
  'conversations' as table_name,
  COUNT(*) as record_count,
  COUNT(CASE WHEN deleted = true THEN 1 END) as deleted_count
FROM ai_solutions_development.dev_assist_pilot.conversations

UNION ALL

SELECT 
  'chat_messages' as table_name,
  COUNT(*) as record_count,
  COUNT(CASE WHEN deleted = true THEN 1 END) as deleted_count
FROM ai_solutions_development.dev_assist_pilot.chat_messages

UNION ALL

SELECT 
  'chat_activity_log' as table_name,
  COUNT(*) as record_count,
  0 as deleted_count
FROM ai_solutions_development.dev_assist_pilot.chat_activity_log;

-- View recent data
SELECT * FROM ai_solutions_development.dev_assist_pilot.conversations 
ORDER BY created_at DESC LIMIT 10;

SELECT * FROM ai_solutions_development.dev_assist_pilot.chat_messages 
ORDER BY created_at DESC LIMIT 10;

SELECT * FROM ai_solutions_development.dev_assist_pilot.chat_activity_log 
ORDER BY timestamp DESC LIMIT 10;


-- ============================================================================
-- ANALYTICS QUERIES
-- ============================================================================
-- Useful queries for monitoring and business intelligence

-- ----------------------------------------------------------------------------
-- Token Usage Analytics
-- ----------------------------------------------------------------------------
-- Token usage by user (last 30 days)
SELECT 
  user_id,
  user_name,
  COUNT(*) as message_count,
  SUM(input_tokens) as total_input_tokens,
  SUM(output_tokens) as total_output_tokens,
  SUM(COALESCE(cache_creation_input_tokens, 0) + COALESCE(cache_read_input_tokens, 0)) as total_cached_tokens,
  SUM(input_tokens + output_tokens) as total_tokens,
  SUM(input_tokens - COALESCE(cache_creation_input_tokens, 0) - COALESCE(cache_read_input_tokens, 0) + output_tokens) as billable_tokens,
  ROUND(
    SUM(COALESCE(cache_creation_input_tokens, 0) + COALESCE(cache_read_input_tokens, 0)) * 100.0 / 
    NULLIF(SUM(input_tokens), 0), 
    2
  ) as cache_hit_rate_pct
FROM ai_solutions_development.dev_assist_pilot.chat_activity_log
WHERE log_date >= CURRENT_DATE - INTERVAL 30 DAYS
  AND message_type = 'assistant'
GROUP BY user_id, user_name
ORDER BY total_tokens DESC;

-- Daily token usage trend
SELECT 
  log_date,
  COUNT(*) as message_count,
  SUM(input_tokens + output_tokens) as total_tokens,
  SUM(input_tokens - COALESCE(cache_creation_input_tokens, 0) - COALESCE(cache_read_input_tokens, 0) + output_tokens) as billable_tokens,
  ROUND(AVG(input_tokens + output_tokens), 0) as avg_tokens_per_message
FROM ai_solutions_development.dev_assist_pilot.chat_activity_log
WHERE log_date >= CURRENT_DATE - INTERVAL 30 DAYS
  AND message_type = 'assistant'
GROUP BY log_date
ORDER BY log_date DESC;

-- ----------------------------------------------------------------------------
-- Conversation Context Tracking
-- ----------------------------------------------------------------------------
-- Calculate current context size for each active conversation
WITH latest_assistant_messages AS (
  SELECT 
    chat_id,
    user_id,
    input_tokens,
    output_tokens,
    ROW_NUMBER() OVER (PARTITION BY chat_id, user_id ORDER BY created_at DESC) as rn
  FROM ai_solutions_development.dev_assist_pilot.chat_messages
  WHERE deleted = FALSE 
    AND role = 'assistant'
),
context_calc AS (
  SELECT 
    chat_id,
    user_id,
    MAX(CASE WHEN rn = 1 THEN input_tokens ELSE 0 END) as last_input_tokens,
    SUM(output_tokens) as total_output_tokens
  FROM latest_assistant_messages
  GROUP BY chat_id, user_id
)
SELECT 
  c.chat_id,
  c.user_id,
  c.title,
  c.message_count,
  cc.last_input_tokens,
  cc.total_output_tokens,
  (cc.last_input_tokens + cc.total_output_tokens) as total_context_tokens,
  ROUND((cc.last_input_tokens + cc.total_output_tokens) / 200000.0 * 100, 2) as context_percentage,
  c.updated_at
FROM ai_solutions_development.dev_assist_pilot.conversations c
JOIN context_calc cc ON c.chat_id = cc.chat_id AND c.user_id = cc.user_id
WHERE c.deleted = FALSE
ORDER BY total_context_tokens DESC
LIMIT 20;

-- ----------------------------------------------------------------------------
-- User Activity Analytics
-- ----------------------------------------------------------------------------
-- Most active users (last 7 days)
SELECT 
  user_name,
  user_id,
  COUNT(DISTINCT chat_id) as conversation_count,
  COUNT(*) as message_count,
  COUNT(DISTINCT DATE(timestamp)) as active_days
FROM ai_solutions_development.dev_assist_pilot.chat_activity_log
WHERE log_date >= CURRENT_DATE - INTERVAL 7 DAYS
GROUP BY user_name, user_id
ORDER BY message_count DESC
LIMIT 20;

-- LLM model usage distribution
SELECT 
  selected_llm,
  COUNT(*) as usage_count,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as usage_pct,
  SUM(input_tokens + output_tokens) as total_tokens,
  ROUND(AVG(input_tokens + output_tokens), 0) as avg_tokens_per_message
FROM ai_solutions_development.dev_assist_pilot.chat_activity_log
WHERE log_date >= CURRENT_DATE - INTERVAL 30 DAYS
  AND message_type = 'assistant'
GROUP BY selected_llm
ORDER BY usage_count DESC;

-- Peak usage hours
SELECT 
  HOUR(timestamp) as hour_of_day,
  COUNT(*) as message_count,
  COUNT(DISTINCT user_id) as unique_users
FROM ai_solutions_development.dev_assist_pilot.chat_activity_log
WHERE log_date >= CURRENT_DATE - INTERVAL 7 DAYS
GROUP BY HOUR(timestamp)
ORDER BY hour_of_day;


-- ============================================================================
-- TROUBLESHOOTING QUERIES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Check Table History (for rollback if needed)
-- ----------------------------------------------------------------------------
-- View recent operations on tables
DESCRIBE HISTORY ai_solutions_development.dev_assist_pilot.conversations LIMIT 10;
DESCRIBE HISTORY ai_solutions_development.dev_assist_pilot.chat_messages LIMIT 10;
DESCRIBE HISTORY ai_solutions_development.dev_assist_pilot.chat_activity_log LIMIT 10;

-- Rollback to previous version if something goes wrong
-- SELECT * FROM ai_solutions_development.dev_assist_pilot.conversations VERSION AS OF 1;
-- RESTORE TABLE ai_solutions_development.dev_assist_pilot.conversations TO VERSION AS OF 1;

-- ----------------------------------------------------------------------------
-- Find Problematic Conversations (Large Context)
-- ----------------------------------------------------------------------------
-- Conversations approaching context limits
SELECT 
  c.chat_id,
  c.user_id,
  c.title,
  c.message_count,
  SUM(m.input_tokens + m.output_tokens) as estimated_context_tokens
FROM ai_solutions_development.dev_assist_pilot.conversations c
JOIN ai_solutions_development.dev_assist_pilot.chat_messages m 
  ON c.chat_id = m.chat_id AND c.user_id = m.user_id
WHERE c.deleted = FALSE 
  AND m.deleted = FALSE
GROUP BY c.chat_id, c.user_id, c.title, c.message_count
HAVING SUM(m.input_tokens + m.output_tokens) > 150000  -- 75% of 200K limit
ORDER BY estimated_context_tokens DESC;

-- ----------------------------------------------------------------------------
-- Data Quality Checks
-- ----------------------------------------------------------------------------
-- Check for orphaned messages (messages without conversations)
SELECT 
  m.chat_id,
  m.user_id,
  COUNT(*) as orphaned_message_count
FROM ai_solutions_development.dev_assist_pilot.chat_messages m
LEFT JOIN ai_solutions_development.dev_assist_pilot.conversations c 
  ON m.chat_id = c.chat_id AND m.user_id = c.user_id
WHERE c.chat_id IS NULL
GROUP BY m.chat_id, m.user_id;

-- Check for conversations with mismatched message counts
SELECT 
  c.chat_id,
  c.user_id,
  c.message_count as recorded_count,
  COUNT(m.message_id) as actual_count,
  c.message_count - COUNT(m.message_id) as difference
FROM ai_solutions_development.dev_assist_pilot.conversations c
LEFT JOIN ai_solutions_development.dev_assist_pilot.chat_messages m 
  ON c.chat_id = m.chat_id AND c.user_id = m.user_id AND m.deleted = FALSE
WHERE c.deleted = FALSE
GROUP BY c.chat_id, c.user_id, c.message_count
HAVING c.message_count != COUNT(m.message_id);

-- Check for NULL values in required fields
SELECT 
  'conversations' as table_name,
  SUM(CASE WHEN chat_id IS NULL THEN 1 ELSE 0 END) as null_chat_id,
  SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as null_user_id,
  SUM(CASE WHEN title IS NULL THEN 1 ELSE 0 END) as null_title,
  SUM(CASE WHEN created_at IS NULL THEN 1 ELSE 0 END) as null_created_at
FROM ai_solutions_development.dev_assist_pilot.conversations

UNION ALL

SELECT 
  'chat_messages' as table_name,
  SUM(CASE WHEN chat_id IS NULL THEN 1 ELSE 0 END) as null_chat_id,
  SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as null_user_id,
  SUM(CASE WHEN content IS NULL THEN 1 ELSE 0 END) as null_content,
  SUM(CASE WHEN created_at IS NULL THEN 1 ELSE 0 END) as null_created_at
FROM ai_solutions_development.dev_assist_pilot.chat_messages;


-- ============================================================================
-- PERFORMANCE TESTING QUERIES
-- ============================================================================
-- Use these to validate that clustering and optimizations are working

-- ----------------------------------------------------------------------------
-- Test Query Performance (Should be fast with clustering)
-- ----------------------------------------------------------------------------
-- Get conversation list for a user (should scan minimal files)
SELECT chat_id, title, message_count, updated_at
FROM ai_solutions_development.dev_assist_pilot.conversations
WHERE user_id = 'test_user_123'
  AND deleted = FALSE
ORDER BY updated_at DESC;

-- Get messages for a conversation (should scan minimal files)
SELECT message_id, role, content, created_at, input_tokens, output_tokens
FROM ai_solutions_development.dev_assist_pilot.chat_messages
WHERE user_id = 'test_user_123'
  AND chat_id = 'test_chat_456'
  AND deleted = FALSE
ORDER BY created_at ASC;

-- Get activity logs for date range (should use clustering efficiently)
SELECT user_name, message_type, selected_llm, input_tokens, output_tokens, timestamp
FROM ai_solutions_development.dev_assist_pilot.chat_activity_log
WHERE log_date >= CURRENT_DATE - INTERVAL 7 DAYS
  AND user_id = 'test_user_123'
ORDER BY timestamp DESC;

-- Check query execution plans (look for "PushedFilters" and file pruning)
-- EXPLAIN EXTENDED 
-- SELECT * FROM conversations WHERE user_id = 'test_user_123';


-- ============================================================================
-- BACKUP AND RECOVERY
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Create Backup Tables (Before major changes)
-- ----------------------------------------------------------------------------
/*
CREATE TABLE ai_solutions_development.dev_assist_pilot.conversations_backup_20240115
AS SELECT * FROM ai_solutions_development.dev_assist_pilot.conversations;

CREATE TABLE ai_solutions_development.dev_assist_pilot.chat_messages_backup_20240115
AS SELECT * FROM ai_solutions_development.dev_assist_pilot.chat_messages;

CREATE TABLE ai_solutions_development.dev_assist_pilot.chat_activity_log_backup_20240115
AS SELECT * FROM ai_solutions_development.dev_assist_pilot.chat_activity_log;
*/

-- ----------------------------------------------------------------------------
-- Restore from Backup
-- ----------------------------------------------------------------------------
/*
-- Option 1: Restore to specific version using time travel
RESTORE TABLE ai_solutions_development.dev_assist_pilot.conversations 
TO VERSION AS OF 5;

-- Option 2: Restore from backup table
INSERT OVERWRITE ai_solutions_development.dev_assist_pilot.conversations
SELECT * FROM ai_solutions_development.dev_assist_pilot.conversations_backup_20240115;
*/

-- ----------------------------------------------------------------------------
-- Export Data (For external backup or migration)
-- ----------------------------------------------------------------------------
/*
-- Export to Parquet files
COPY (SELECT * FROM ai_solutions_development.dev_assist_pilot.conversations)
TO '/dbfs/backups/conversations/' 
FILEFORMAT = PARQUET;

-- Export to Delta table in different location
CREATE TABLE ai_solutions_development.backup.conversations
LOCATION '/mnt/backup/conversations'
AS SELECT * FROM ai_solutions_development.dev_assist_pilot.conversations;
*/


-- ----------------------------------------------------------------------------
-- Change Column Comments
-- ----------------------------------------------------------------------------
/*
ALTER TABLE ai_solutions_development.dev_assist_pilot.chat_messages
ALTER COLUMN input_tokens COMMENT 'Cumulative context tokens sent to LLM (includes system prompt + history)';

ALTER TABLE ai_solutions_development.dev_assist_pilot.chat_messages
ALTER COLUMN output_tokens COMMENT 'Response tokens generated by LLM';
*/


-- ============================================================================
-- PRODUCTION DEPLOYMENT CHECKLIST
-- ============================================================================
/*
DEPLOYING TO PRODUCTION:

1. CONFIGURATION
   ☐ Update USE CATALOG and USE SCHEMA for production environment
   ☐ Verify table properties match production requirements
   ☐ Review retention policies (log/file retention durations)

2. PERMISSIONS
   ☐ Grant appropriate SELECT/INSERT/UPDATE permissions to application service accounts
   ☐ Grant SELECT permissions to analytics/BI users
   ☐ Restrict DROP/ALTER permissions to admins only
   ☐ Set up Unity Catalog policies if applicable

3. MONITORING
   ☐ Set up table size monitoring (alert if > X GB)
   ☐ Set up query performance monitoring
   ☐ Set up deletion vector ratio monitoring (alert if > 50%)
   ☐ Set up file count monitoring (alert if too many small files)
   ☐ Monitor token usage and costs

4. MAINTENANCE
   ☐ Schedule daily OPTIMIZE jobs (during low-traffic hours)
   ☐ Schedule weekly VACUUM jobs
   ☐ Schedule monthly full optimization
   ☐ Schedule data retention cleanup (delete old activity logs)
   ☐ Set up backup strategy

5. DOCUMENTATION
   ☐ Document table schemas and relationships
   ☐ Document access patterns and query examples
   ☐ Document maintenance procedures
   ☐ Document rollback procedures
   ☐ Document token calculation logic

6. TESTING
   ☐ Load test with production-like data volumes
   ☐ Test query performance with clustering
   ☐ Test update performance with deletion vectors
   ☐ Test backup and restore procedures
   ☐ Test time travel and rollback
   ☐ Verify auto-compact is working

7. DISASTER RECOVERY
   ☐ Document backup locations
   ☐ Test restore from backup
   ☐ Document RTO/RPO requirements
   ☐ Set up cross-region replication if needed
*/


-- ============================================================================
-- OPTIMIZATION TIPS
-- ============================================================================
/*
PERFORMANCE BEST PRACTICES:

1. CLUSTERING
   - Tables are already clustered by primary access patterns
   - Clustering is maintained automatically with writes

2. UPDATES
   - Batch updates when possible (reduces file fragmentation)
   - Use MERGE for upserts instead of DELETE + INSERT
   - Let auto-compact handle small file cleanup

3. QUERIES
   - Always filter by clustered columns (user_id, chat_id, log_date)
   - Use deleted = FALSE in WHERE clauses for soft deletes
   - Avoid SELECT * - specify only needed columns
   - Use LIMIT for exploratory queries

4. MAINTENANCE
   - Run OPTIMIZE weekly or when deletion_vector_ratio > 50%
   - Run VACUUM monthly to reclaim storage
   - Monitor table sizes and file counts
   - Don't over-optimize - trust auto-compact for routine maintenance

5. SCHEMA CHANGES
   - Use column mapping mode for safe renames
   - Use time travel to rollback if needed

6. COST OPTIMIZATION
   - Monitor token usage and caching effectiveness
   - Archive old activity logs to cheaper storage
   - Use VACUUM to reclaim storage from deleted data
   - Consider table archival strategy for old conversations
*/