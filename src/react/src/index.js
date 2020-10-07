import "./assets/styles.scss";
import getRoutes from "./Routes";

let harnessApi = null;

function setHarnessApi(api) {
    harnessApi = api;
}

export {
    getRoutes,
    setHarnessApi,
    harnessApi
};
