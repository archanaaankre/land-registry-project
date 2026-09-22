import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:5000/api", // Flask backend, phase 3
});

export default api;
