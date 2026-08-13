import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { SortableColumnHeader } from "@/components/table/sortable-column-header";
import { useScreeningUiStore, type ScreeningProfileSortField } from "@/store/screening-ui-store";
import type { ScreeningProfile } from "@/types/screening";

export interface ScreeningProfileTableProps {
  profiles: ScreeningProfile[];
  onRename: (profile: ScreeningProfile) => void;
  onDuplicate: (profile: ScreeningProfile) => void;
  onDelete: (profile: ScreeningProfile) => void;
}

interface RowActionsProps {
  profile: ScreeningProfile;
  onRename: (profile: ScreeningProfile) => void;
  onDuplicate: (profile: ScreeningProfile) => void;
  onDelete: (profile: ScreeningProfile) => void;
}

function RowActions({ profile, onRename, onDuplicate, onDelete }: RowActionsProps): ReactNode {
  return (
    <div className="flex justify-end gap-1">
      <button
        type="button"
        onClick={() => {
          onRename(profile);
        }}
        className="rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      >
        Rename
      </button>
      <button
        type="button"
        onClick={() => {
          onDuplicate(profile);
        }}
        className="rounded-md px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      >
        Duplicate
      </button>
      <button
        type="button"
        onClick={() => {
          onDelete(profile);
        }}
        className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
      >
        Delete
      </button>
    </div>
  );
}

export function ScreeningProfileTable({ profiles, onRename, onDuplicate, onDelete }: ScreeningProfileTableProps): ReactNode {
  const sort = useScreeningUiStore((state) => state.sort);
  const direction = useScreeningUiStore((state) => state.direction);
  const setSort = useScreeningUiStore((state) => state.setSort);

  function handleSort(field: ScreeningProfileSortField): void {
    setSort(field);
  }

  return (
    <>
      <table className="hidden w-full text-sm sm:table">
        <caption className="sr-only">Screening profiles</caption>
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800">
            <SortableColumnHeader label="Name" field="name" activeField={sort} direction={direction} onSort={handleSort} />
            <th scope="col" className="px-3 py-2 text-left text-xs font-semibold text-slate-500 dark:text-slate-400">
              Filters
            </th>
            <SortableColumnHeader label="Created" field="created_at" activeField={sort} direction={direction} onSort={handleSort} />
            <SortableColumnHeader label="Updated" field="updated_at" activeField={sort} direction={direction} onSort={handleSort} />
            <th scope="col" className="px-3 py-2 text-right text-xs font-semibold text-slate-500 dark:text-slate-400">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {profiles.map((profile) => (
            <tr key={profile.id} className="border-b border-slate-100 dark:border-slate-800/60">
              <td className="px-3 py-2">
                <Link
                  to="/screening/$profileId"
                  params={{ profileId: profile.id }}
                  className="font-medium text-brand-700 hover:underline dark:text-brand-400"
                >
                  {profile.name}
                </Link>
                {profile.description && <p className="text-xs text-slate-500 dark:text-slate-400">{profile.description}</p>}
              </td>
              <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{profile.filters.length}</td>
              <td className="px-3 py-2 text-slate-500 dark:text-slate-400">{new Date(profile.created_at).toLocaleDateString()}</td>
              <td className="px-3 py-2 text-slate-500 dark:text-slate-400">{new Date(profile.updated_at).toLocaleDateString()}</td>
              <td className="px-3 py-2">
                <RowActions profile={profile} onRename={onRename} onDuplicate={onDuplicate} onDelete={onDelete} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <ul className="flex flex-col gap-3 sm:hidden">
        {profiles.map((profile) => (
          <li key={profile.id} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
            <Link
              to="/screening/$profileId"
              params={{ profileId: profile.id }}
              className="font-medium text-brand-700 hover:underline dark:text-brand-400"
            >
              {profile.name}
            </Link>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {profile.filters.length} filters · Updated {new Date(profile.updated_at).toLocaleDateString()}
            </p>
            <div className="mt-2">
              <RowActions profile={profile} onRename={onRename} onDuplicate={onDuplicate} onDelete={onDelete} />
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
