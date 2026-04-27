-- 1) Canonical tenants table (one row per business/customer)
create table if not exists public.tenants (
  id varchar(64) primary key,
  name varchar(255) not null default '',
  is_active integer not null default 1,
  created_at timestamptz not null default timezone('utc', now()),
  constraint chk_tenants_active check (is_active in (0, 1))
);

-- 2) Backfill tenants from existing tenant_id values across current tables
insert into public.tenants (id, name)
select tenant_id, initcap(replace(tenant_id, '-', ' '))
from (
  select tenant_id from public.users
  union
  select tenant_id from public.tenant_memberships
  union
  select tenant_id from public.app_sessions
  union
  select tenant_id from public.tenant_apps
  union
  select tenant_id from public.inventory_items
  union
  select tenant_id from public.inventory_movements
  union
  select tenant_id from public.employees
  union
  select tenant_id from public.time_events
  union
  select tenant_id from public.shifts
  union
  select tenant_id from public.time_policies
  union
  select tenant_id from public.timesheet_approvals
  union
  select tenant_id from public.manager_alerts
  union
  select tenant_id from public.audit_logs
  union
  select tenant_id from public.messages
) all_tenants
where tenant_id is not null and tenant_id <> ''
on conflict (id) do nothing;

-- 3) Add foreign keys from tenant-scoped tables to tenants(id)
-- NOT VALID lets this add safely first, then we validate.
alter table public.tenant_apps
  add constraint fk_tenant_apps_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.users
  add constraint fk_users_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.tenant_memberships
  add constraint fk_tenant_memberships_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.app_sessions
  add constraint fk_app_sessions_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.inventory_items
  add constraint fk_inventory_items_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.inventory_movements
  add constraint fk_inventory_movements_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.employees
  add constraint fk_employees_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.time_events
  add constraint fk_time_events_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.shifts
  add constraint fk_shifts_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.time_policies
  add constraint fk_time_policies_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.timesheet_approvals
  add constraint fk_timesheet_approvals_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.manager_alerts
  add constraint fk_manager_alerts_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.audit_logs
  add constraint fk_audit_logs_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

alter table public.messages
  add constraint fk_messages_tenant
  foreign key (tenant_id) references public.tenants(id) on delete cascade not valid;

-- 4) Validate all new FK constraints after backfill
alter table public.tenant_apps validate constraint fk_tenant_apps_tenant;
alter table public.users validate constraint fk_users_tenant;
alter table public.tenant_memberships validate constraint fk_tenant_memberships_tenant;
alter table public.app_sessions validate constraint fk_app_sessions_tenant;
alter table public.inventory_items validate constraint fk_inventory_items_tenant;
alter table public.inventory_movements validate constraint fk_inventory_movements_tenant;
alter table public.employees validate constraint fk_employees_tenant;
alter table public.time_events validate constraint fk_time_events_tenant;
alter table public.shifts validate constraint fk_shifts_tenant;
alter table public.time_policies validate constraint fk_time_policies_tenant;
alter table public.timesheet_approvals validate constraint fk_timesheet_approvals_tenant;
alter table public.manager_alerts validate constraint fk_manager_alerts_tenant;
alter table public.audit_logs validate constraint fk_audit_logs_tenant;
alter table public.messages validate constraint fk_messages_tenant;

