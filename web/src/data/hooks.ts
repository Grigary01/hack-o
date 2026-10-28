import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { dataSource } from './source';
import type { SearchParams } from './types';

export const keys = {
  health: ['health'] as const,
  suggestions: ['suggestions'] as const,
  search: (p: SearchParams) => ['search', p] as const,
  hotel: (id: string, p: SearchParams | null) => ['hotel', id, p] as const,
  hotelierHotels: ['hotelier', 'hotels'] as const,
  questions: (hotelId: string) => ['hotelier', 'questions', hotelId] as const,
  question: (id: string) => ['hotelier', 'question', id] as const,
  answer: (id: string) => ['hotelier', 'answer', id] as const,
  publish: (id: string) => ['hotelier', 'publish', id] as const,
  facts: (hotelId: string) => ['hotelier', 'facts', hotelId] as const,
  rooms: (hotelId: string) => ['hotelier', 'rooms', hotelId] as const,
};

export const useHealth = () => useQuery({ queryKey: keys.health, queryFn: () => dataSource.getHealth(), staleTime: 60_000 });

export const useSuggestions = () =>
  useQuery({ queryKey: keys.suggestions, queryFn: () => dataSource.getSuggestions(), staleTime: Infinity });

export const useSearch = (params: SearchParams) =>
  useQuery({ queryKey: keys.search(params), queryFn: () => dataSource.search(params), enabled: params.text.trim().length > 0 });

export const useHotel = (hotelId: string, params: SearchParams | null) =>
  useQuery({ queryKey: keys.hotel(hotelId, params), queryFn: () => dataSource.getHotel(hotelId, params) });

export function useRequestCheck() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ hotelId, featureKeys }: { hotelId: string; featureKeys: string[] }) => dataSource.requestCheck(hotelId, featureKeys),
    onSuccess: () => client.invalidateQueries({ queryKey: ['hotelier'] }),
  });
}

export const useHotelierHotels = () => useQuery({ queryKey: keys.hotelierHotels, queryFn: () => dataSource.listHotelierHotels() });

export const useQuestions = (hotelId: string) =>
  useQuery({ queryKey: keys.questions(hotelId), queryFn: () => dataSource.listQuestions(hotelId) });

export const useQuestion = (questionId: string) =>
  useQuery({ queryKey: keys.question(questionId), queryFn: () => dataSource.getQuestion(questionId) });

export function useSubmitAnswer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ questionId, text }: { questionId: string; text: string }) => dataSource.submitAnswer(questionId, text),
    onSuccess: (answer) => client.setQueryData(keys.answer(answer.id), answer),
  });
}

export const useAnswer = (answerId: string) =>
  useQuery({ queryKey: keys.answer(answerId), queryFn: () => dataSource.getAnswer(answerId), retry: false });

export function useRejectAnswer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (answerId: string) => dataSource.rejectAnswer(answerId),
    onSuccess: (_data, answerId) => client.invalidateQueries({ queryKey: keys.answer(answerId) }),
  });
}

export function usePublishAnswer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ answerId, overrides }: { answerId: string; overrides: Record<string, boolean> }) =>
      dataSource.publishAnswer(answerId, overrides),
    onSuccess: async (result) => {
      client.setQueryData(keys.publish(result.answerId), result);
      // Опубликованный ответ сразу влияет на подбор гостей и на кабинет.
      // refetchType: 'all' — чтобы и закрытые сейчас экраны не показали устаревшее при возврате.
      await Promise.all([
        client.invalidateQueries({ queryKey: ['hotelier'], refetchType: 'all' }),
        client.invalidateQueries({ queryKey: ['search'] }),
        client.invalidateQueries({ queryKey: ['hotel'] }),
      ]);
    },
  });
}

export const usePublishResult = (answerId: string) =>
  useQuery({ queryKey: keys.publish(answerId), queryFn: () => dataSource.getPublishResult(answerId), retry: false });

export const useFacts = (hotelId: string) => useQuery({ queryKey: keys.facts(hotelId), queryFn: () => dataSource.getFacts(hotelId) });

export const useRooms = (hotelId: string) => useQuery({ queryKey: keys.rooms(hotelId), queryFn: () => dataSource.getRooms(hotelId) });

export function useResetDemo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await dataSource.resetDemo?.();
    },
    onSuccess: () => client.invalidateQueries(),
  });
}
