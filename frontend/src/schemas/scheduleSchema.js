import { z } from 'zod';

export const scheduleFormSchema = z.object({
  document_id: z.coerce.number().min(1, 'Please select a valid HLA document / control'),
  name: z.string().min(2, 'Schedule name must be at least 2 characters'),
  hostname: z.string().min(1, 'Execution hostname / server host is required'),
  environment: z.enum(['dev', 'prod']),
  schedule_type: z.enum(['daily', 'hourly', 'weekly', 'monthly', 'interval', 'custom_cron']),
  run_time: z.string().optional().default('02:00'),
  days_of_week: z.string().optional().default('mon,tue,wed,thu,fri'),
  day_of_month: z.string().optional().default('1'),
  interval_minutes: z.coerce.number().min(1).optional().default(60),
  cron_expression: z.string().optional().default('0 2 * * *'),
  timezone: z.string().default('UTC'),
  notification_emails: z.string().optional().default(''),
  notify_on_failure: z.boolean().optional().default(true),
});

