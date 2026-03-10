SELECT pid, usename, application_name, client_addr, state, query
FROM pg_stat_activity
WHERE state = 'idle';

SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
where state = 'idle' and usename = 'postgres';