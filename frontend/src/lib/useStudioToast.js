import { toast as notify } from "sonner";
const toast = ({ title, description, variant }) => variant === "destructive" ? notify.error(title, { description }) : notify.success(title, { description });
export const useStudioToast = () => ({ toast });
