import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from './api';

// Query Keys
export const queryKeys = {
  projects: ['projects'],
  project: (id) => ['projects', id],
  schedules: (projectId) => ['projects', projectId, 'schedules'],
  targetArtifacts: (docId) => ['documents', docId, 'targetArtifacts'],
};

// Fetch list of all projects
export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects,
    queryFn: async () => {
      const { data } = await api.get('/api/projects');
      return data.projects || [];
    },
  });
}

// Fetch single project details
export function useProjectDetails(projectId) {
  return useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: async () => {
      if (!projectId) return null;
      const { data } = await api.get(`/api/projects/${projectId}`);
      return data;
    },
    enabled: !!projectId,
  });
}

// Fetch schedules for project
export function useControlSchedules(projectId) {
  return useQuery({
    queryKey: queryKeys.schedules(projectId),
    queryFn: async () => {
      if (!projectId) return [];
      const { data } = await api.get(`/api/projects/${projectId}/schedules`);
      return data.schedules || [];
    },
    enabled: !!projectId,
  });
}

// Mutation to create a control schedule
export function useCreateSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ projectId, scheduleData }) => {
      const { data } = await api.post(`/api/projects/${projectId}/schedules`, scheduleData);
      return data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.schedules(variables.projectId) });
    },
  });
}
