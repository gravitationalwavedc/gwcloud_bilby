import { getStatusType } from '../getVariants';
import { Row, Col } from 'react-bootstrap';

const StatusDisplay = ({ name, date }) => (
    <Row>
        <Col md="auto" className={'text-uppercase ' + getStatusType(name)}>
            {name}
        </Col>
        <Col md="auto" className="px-0">
            {' '}
            -{' '}
        </Col>
        <Col md="auto">{date}</Col>
    </Row>
);

export default StatusDisplay;
