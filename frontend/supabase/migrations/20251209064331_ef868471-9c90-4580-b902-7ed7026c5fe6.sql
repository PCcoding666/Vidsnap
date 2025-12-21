-- Enable Row Level Security on schema_versions table
ALTER TABLE public.schema_versions ENABLE ROW LEVEL SECURITY;

-- Create a restrictive policy that denies all access (this is internal metadata)
CREATE POLICY "deny_all_access" ON public.schema_versions
FOR ALL USING (false);