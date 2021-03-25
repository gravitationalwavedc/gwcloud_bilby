from types import SimpleNamespace

bilby_parameters = SimpleNamespace()

bilby_parameters.SIMULATED = ["simulated", "Simulated"]
bilby_parameters.REAL = ["real", "Real"]

bilby_parameters.HANFORD = ["hanford", "Hanford"]
bilby_parameters.LIVINGSTON = ["livingston", "Livingston"]
bilby_parameters.VIRGO = ["virgo", "Virgo"]
bilby_parameters.SIGNAL_DURATION = ["signal_duration", "Signal Duration (s)"]
bilby_parameters.SAMPLING_FREQUENCY = ["sampling_frequency", "Sampling Frequency (Hz)"]
bilby_parameters.TRIGGER_TIME = ["trigger_time", "Trigger Time"]
bilby_parameters.HANFORD_MIN_FREQ = ["hanford_minimum_frequency", "Hanford Minimum Frequency"]
bilby_parameters.HANFORD_MAX_FREQ = ["hanford_maximum_frequency", "Hanford Maximum Frequency"]
bilby_parameters.HANFORD_CHANNEL = ["hanford_channel", "Hanford Channel"]
bilby_parameters.LIVINGSTON_MIN_FREQ = ["livingston_minimum_frequency", "Livingston Minimum Frequency"]
bilby_parameters.LIVINGSTON_MAX_FREQ = ["livingston_maximum_frequency", "Livingston Maximum Frequency"]
bilby_parameters.LIVINGSTON_CHANNEL = ["livingston_channel", "Livingston Channel"]
bilby_parameters.VIRGO_MIN_FREQ = ["virgo_minimum_frequency", "Virgo Minimum Frequency"]
bilby_parameters.VIRGO_MAX_FREQ = ["virgo_maximum_frequency", "Virgo Maximum Frequency"]
bilby_parameters.VIRGO_CHANNEL = ["virgo_channel", "Virgo Channel"]

bilby_parameters.SKIP = ["skip", "None"]
bilby_parameters.BBH = ["binaryBlackHole", "Binary Black Hole"]
bilby_parameters.BNS = ["binaryNeutronStar", "Binary Neutron Star"]

bilby_parameters.PRIOR_4S = ["4s", "4s"]
bilby_parameters.PRIOR_8S = ["8s", "8s"]
bilby_parameters.PRIOR_16S = ["16s", "16s"]
bilby_parameters.PRIOR_32S = ["32s", "32s"]
bilby_parameters.PRIOR_64S = ["64s", "64s"]
bilby_parameters.PRIOR_128S = ["128s", "128s"]

bilby_parameters.MASS1 = ["mass1", "Mass 1"]
bilby_parameters.MASS2 = ["mass2", "Mass 2"]
bilby_parameters.LUMINOSITY_DISTANCE = ["luminosity_distance", "Luminosity Distance (Mpc)"]
bilby_parameters.IOTA = ["iota", "iota"]
bilby_parameters.PSI = ["psi", "psi"]
bilby_parameters.PHASE = ["phase", "Phase"]
bilby_parameters.MERGER = ["merger_time", "Merger Time (GPS Time)"]
bilby_parameters.RA = ["ra", "Right Ascension (Radians)"]
bilby_parameters.DEC = ["dec", "Declination (Degrees)"]

bilby_parameters.FIXED = ["fixed", "Fixed"]
bilby_parameters.UNIFORM = ["uniform", "Uniform"]

bilby_parameters.DYNESTY = ["dynesty", "Dynesty"]
bilby_parameters.NESTLE = ["nestle", "Nestle"]
bilby_parameters.EMCEE = ["emcee", "Emcee"]

bilby_parameters.NLIVE = ["nlive", "Number of live points"]
bilby_parameters.NACT = ["nact", "Number of auto-correlation steps"]
bilby_parameters.MAXMCMC = ["maxmcmc", "Maximum number of steps"]
bilby_parameters.WALKS = ["walks", "Minimum number of walks"]
bilby_parameters.DLOGZ = ["dlogz", "Stopping criteria"]
bilby_parameters.CPUS = ["cpus", "Number of CPUs to use for parallelisation"]
