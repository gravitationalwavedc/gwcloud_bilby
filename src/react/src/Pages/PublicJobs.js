import React, { useState, useEffect } from 'react';
import {createPaginationContainer, graphql} from 'react-relay';
import { Button, Container, Col, Form, InputGroup, Row } from 'react-bootstrap';
import { HiOutlineSearch, HiOutlinePlus } from 'react-icons/hi';
import Link from 'found/Link';
import JobTable from '../Components/JobTable';

const RECORDS_PER_PAGE = 100;

const PublicJobs = ({data, match, router, relay}) => {
    const [search, setSearch] = useState('');
    const [timeRange, setTimeRange] = useState('1d');
    const [order, setOrder] = useState();
    const [direction, setDirection] = useState('descending');

    useEffect(() => handleSearchChange(), [search, timeRange, direction, order]);

    const handleSearchChange = () => {
        const refetchVariables = {
            count: RECORDS_PER_PAGE,
            search: search,
            timeRange: timeRange,
            orderBy: order,
            direction: direction
        };
        relay.refetchConnection(1, null, refetchVariables);
    };

    const loadMore = () => {
        if (relay.hasMore()) {
            relay.loadMore(RECORDS_PER_PAGE);
        }
    };

    const timeOptions = [
        {text: 'Any time', value: 'all'},
        {text: 'Past 24 hours', value: '1d'},
        {text: 'Past week', value: '1w'},
        {text: 'Past month', value: '1m'},
        {text: 'Past year', value: '1y'},
    ];

    return (
        <Container >
            <h1 className="pt-5 mb-4">
            Public Jobs
                <span className="float-right">
                    <Link 
                        as={Button}
                        variant="outline-primary"
                        to='/bilby/job-list/' 
                        exact 
                        match={match} 
                        router={router} 
                        className="mr-1">
                          Switch to my jobs
                    </Link>
                    <Link as={Button} to='/bilby/job-form/' exact match={match} router={router}>
                        <HiOutlinePlus size={18} className="mb-1 mr-1"/>
                        Start a new job 
                    </Link>
                </span>
            </h1>
            <Form>
                <Form.Row>
                    <Col lg={3}>
                        <Form.Group controlId="searchJobs">
                            <Form.Label srOnly>
                              Search
                            </Form.Label>
                            <InputGroup>
                                <InputGroup.Prepend>
                                    <InputGroup.Text>
                                        <HiOutlineSearch />
                                    </InputGroup.Text>
                                </InputGroup.Prepend>
                                <Form.Control 
                                    placeholder="Find a job..." 
                                    value={search} 
                                    onChange={({target}) => setSearch(target.value)} />
                            </InputGroup>
                        </Form.Group>
                    </Col>
                    <Col lg={3}>
                        <Form.Group controlId="timeRange">
                            <Form.Label srOnly>
                              Time
                            </Form.Label>
                            <Form.Control 
                                as="select" 
                                value={timeRange} 
                                onChange={({target}) => setTimeRange(target.value)} 
                                custom>
                                {timeOptions.map(option => 
                                    <option 
                                        key={option.value} 
                                        value={option.value}>
                                        {option.text}
                                    </option>
                                )}
                            </Form.Control>
                        </Form.Group>
                    </Col>
                </Form.Row>
            </Form>
            <Row>
                <Col>
                    <JobTable
                        data={data.publicBilbyJobs} 
                        setOrder={setOrder} 
                        order={order} 
                        setDirection={setDirection} 
                        direction={direction}
                        match={match}
                        router={router}
                        hasMore={relay.hasMore()}
                        loadMore={loadMore}
                    />
                </Col>
            </Row>
        </Container>
    );
};

export default createPaginationContainer(PublicJobs,
    {
        data: graphql`
            fragment PublicJobs_data on Query {
                publicBilbyJobs(
                    first: $count,
                    after: $cursor,
                    search: $search,
                    timeRange: $timeRange
                ) @connection(key: "PublicJobs_publicBilbyJobs") {
                    pageInfo {
                      hasNextPage
                      endCursor
                    }
                    edges {
                        node {
                            id
                            user
                            name
                            description
                            jobStatus {
                              name
                            }
                            labels {
                                name
                            }
                        }
                    }
                }
            }
        `,
    },
    {
        direction: 'forward',
        query: graphql`
            query PublicJobsForwardQuery(
                $count: Int!,
                $cursor: String,
                $search: String,
                $timeRange: String
            ) {
              ...PublicJobs_data
            }
        `,

        getConnectionFromProps(props) {
            return props.data && props.data.publicBilbyJobs;
        },

        getFragmentVariables(previousVariables, totalCount) {
            return {
                ...previousVariables,
                count: totalCount
            };
        },
        getVariables(props, {count, cursor}, {}) {
            return {
                count,
                cursor
            };
        }
    }
);
