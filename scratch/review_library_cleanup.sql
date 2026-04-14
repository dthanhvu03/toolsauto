-- STEP 1: Count duplicate URLs that will be merged by the new canonical logic
-- (Matches based on rtrim trailing slash, lowercase, and web.facebook.com -> www.facebook.com)

SELECT 
    canonical_url,
    COUNT(*) as entry_count,
    GROUP_CONCAT(post_url, ' | ') as variations
FROM (
    SELECT 
        post_url,
        REPLACE(REPLACE(RTRIM(LOWER(post_url), '/'), 'web.facebook.com', 'www.facebook.com'), '/reels/', '/reel/') as canonical_url
    FROM page_insights
)
GROUP BY canonical_url
HAVING COUNT(*) > 1
ORDER BY entry_count DESC
LIMIT 50;


-- STEP 2: Identify rows with "Views: XXX" pattern in caption
-- These are legacy/buggy records where the view count was captured as caption

SELECT id, page_name, caption, views, post_url, recorded_at
FROM page_insights
WHERE caption LIKE 'Views: %' OR caption LIKE 'View: %'
ORDER BY recorded_at DESC
LIMIT 100;


-- STEP 3: Summary of rows targeted for deletion (Audit only)
-- We will delete the older/cruder records if they have a better match, or just delete the bad captions.

-- TO DELETE (Review row count below):
-- SELECT COUNT(*) FROM page_insights WHERE caption LIKE 'Views: %';
