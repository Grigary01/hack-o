import { Navigate } from 'react-router-dom';
import { GuestLayout } from '../../components/layout/GuestLayout';
import { EmptyState, ErrorState, Loading } from '../../components/ui/StateView';
import { useHotelierHotels } from '../../data';

/** Авторизации нет: открываем отель, у которого больше всего открытых вопросов. */
export function CabinetIndex() {
  const hotels = useHotelierHotels();
  if (hotels.isPending) {
    return (
      <GuestLayout>
        <Loading label="Открываем кабинет отельера…" />
      </GuestLayout>
    );
  }
  if (hotels.isError) {
    return (
      <GuestLayout>
        <ErrorState title="Кабинет недоступен" error={hotels.error} onRetry={() => hotels.refetch()} />
      </GuestLayout>
    );
  }
  const first = hotels.data[0];
  if (!first) {
    return (
      <GuestLayout>
        <EmptyState title="Отелей пока нет">
          <p>Каталог отелей пока пуст. Попробуйте зайти позже.</p>
        </EmptyState>
      </GuestLayout>
    );
  }
  return <Navigate to={`/hotelier/${encodeURIComponent(first.id)}/questions`} replace />;
}
