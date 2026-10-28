import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { ScrollToTop } from './components/layout/ScrollToTop';
import { HomePage } from './pages/HomePage';
import { ResultsPage } from './pages/ResultsPage';
import { HotelPage } from './pages/HotelPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { CabinetIndex } from './pages/hotelier/CabinetIndex';
import { CabinetLayout } from './pages/hotelier/CabinetLayout';
import { OverviewPage } from './pages/hotelier/OverviewPage';
import { QuestionsPage } from './pages/hotelier/QuestionsPage';
import { AnswerPage } from './pages/hotelier/AnswerPage';
import { ReviewPage } from './pages/hotelier/ReviewPage';
import { PublishedPage } from './pages/hotelier/PublishedPage';
import { FactsPage } from './pages/hotelier/FactsPage';
import { RoomsPage } from './pages/hotelier/RoomsPage';

export function App() {
  return (
    <BrowserRouter>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/search" element={<ResultsPage />} />
        <Route path="/hotels/:hotelId" element={<HotelPage />} />
        <Route path="/hotelier" element={<CabinetIndex />} />
        <Route path="/hotelier/:hotelId" element={<CabinetLayout />}>
          <Route index element={<Navigate to="questions" replace />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="questions" element={<QuestionsPage />} />
          <Route path="questions/:questionId" element={<AnswerPage />} />
          <Route path="answers/:answerId/review" element={<ReviewPage />} />
          <Route path="answers/:answerId/published" element={<PublishedPage />} />
          <Route path="facts" element={<FactsPage />} />
          <Route path="rooms" element={<RoomsPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </BrowserRouter>
  );
}
