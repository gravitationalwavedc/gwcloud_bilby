import { useState, useRef } from 'react';
import { Button, Container, Fade, Overlay, OverlayTrigger, Popover, Row, Tooltip } from 'react-bootstrap';

const CheckButton = ({ content, cancelContent, onClick, ...props }) => {
    const [open, setOpen] = useState(false);
    const target = useRef(null);

    const handleYes = () => {
        setOpen(false);
        onClick();
    };

    return (
        <>
            <Button ref={target} onClick={() => setOpen(true)} {...props}>
                {content}
            </Button>
            <Overlay placement="right" target={target.current} show={open}>
                {(props) => (
                    <Popover {...props} id="button-popover">
                        <Popover.Title as="h3" className="bg-light">
                            Are you sure?
                        </Popover.Title>
                        <Popover.Content>
                            <Container>
                                <Row className="text text-secondary">{cancelContent}</Row>
                                <Row>
                                    <Button variant="outline-success" onClick={() => handleYes()}>
                                        Yes
                                    </Button>
                                    <Button variant="text text-danger" onClick={() => setOpen(false)}>
                                        No
                                    </Button>
                                </Row>
                            </Container>
                        </Popover.Content>
                    </Popover>
                )}
            </Overlay>
        </>
    );
};

const CopyButton = ({ content, copyContent, ...props }) => {
    const handleClick = () => {
        navigator.clipboard.writeText(copyContent);
    };

    const renderTooltip = (props) => {
        return (
            <Tooltip id="button-tooltip" {...props}>
                Token copied!
            </Tooltip>
        );
    };

    return (
        <OverlayTrigger placement="right" overlay={renderTooltip} rootClose trigger="click">
            <Button onClick={handleClick} {...props}>
                {content}
            </Button>
        </OverlayTrigger>
    );
};

const SpoilerButton = ({ content, hiddenContent }) => {
    const [fadeout, setFadeout] = useState(false);
    const [clicked, setClicked] = useState(false);

    return (
        <>
            <Fade in={clicked} mountOnEnter={true}>
                <div>{hiddenContent}</div>
            </Fade>
            <Fade in={!fadeout} unmountOnExit={true} onExited={() => setClicked(true)}>
                <Button variant="text text-secondary" onClick={() => setFadeout(true)}>
                    {content}
                </Button>
            </Fade>
        </>
    );
};

export { CheckButton, CopyButton, SpoilerButton };
