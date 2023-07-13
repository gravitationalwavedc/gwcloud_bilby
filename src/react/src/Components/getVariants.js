const getBadgeType = (name) => {
  const variants = {
    Completed: "primary",
    Error: "danger",
    Running: "info",
    Unknown: "dark",
    "Production Run": "success",
    "Bad Run": "danger",
    "Review Requested": "secondary",
    Reviewed: "info",
    Official: "warning",
  };

  return variants[name];
};

const getStatusType = (name) => {
  const variants = {
    Completed: "text-success",
    Error: "text-danger",
    Running: "text-info",
    Unknown: "text-muted",
  };

  return variants[name];
};

export { getBadgeType, getStatusType };
