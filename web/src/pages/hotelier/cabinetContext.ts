import { useOutletContext } from 'react-router-dom';

export interface CabinetContext {
  hotelId: string;
  hotelName: string;
  base: string;
}

export const useCabinet = () => useOutletContext<CabinetContext>();
