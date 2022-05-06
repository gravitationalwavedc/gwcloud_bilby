def get_patched_bilby_input(klass, *args, **kwargs):
    """
    Returns a modified bilby_pipe Input() or DataGenerationInput() (as klass) object that works as expected via
    patching certain functions as required.
    """
    # Create the instance without calling the constructor (Prevents functions we want to patch firing before we've
    # patched them)
    bilby_input = klass.__new__(klass)

    # _validate_psd_dict was added in 1.0.6 and requires that the psd files really exist on disk - this is not a valid
    # case for us. See https://git.ligo.org/lscsoft/bilby_pipe/-/merge_requests/445
    bilby_input._validate_psd_dict = lambda: "stubbed _validate_psd_dict"

    # Call the init
    bilby_input.__init__(*args, **kwargs)

    return bilby_input