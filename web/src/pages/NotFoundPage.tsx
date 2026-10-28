import { GuestLayout } from '../components/layout/GuestLayout';
import { ButtonLink } from '../components/ui/Button';
import { EmptyState } from '../components/ui/StateView';

export function NotFoundPage() {
  return (
    <GuestLayout>
      <EmptyState title="Такой страницы нет" action={<ButtonLink to="/">На главную</ButtonLink>}>
        <p>Возможно, ссылка устарела. Начните новый поиск или откройте кабинет отельера.</p>
      </EmptyState>
    </GuestLayout>
  );
}
